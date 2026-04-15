"""Async image downloader with token-bucket rate limiting and circuit breaker."""

import asyncio
import random
from pathlib import Path
from urllib.parse import urlparse

import httpx
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from .models import PhotoRecord

_console = Console(stderr=True)

_MAX_ATTEMPTS = 12       # covers multiple circuit-breaker cycles
_BASE_429_DELAY = 30.0   # seconds for first rate-limit backoff
_BASE_5XX_DELAY = 2.0    # seconds for first 5xx/timeout retry
_CIRCUIT_THRESHOLD = 4   # distinct rate-limit events before circuit opens
_CIRCUIT_RESET = 600.0   # seconds to wait when circuit is open (10 min)


def _get_download_url(photo: PhotoRecord) -> str | None:
    """Pick best available URL: original → large → medium."""
    return photo.original_url or photo.large_url or photo.medium_url


def _get_extension(url: str) -> str:
    """Extract file extension from URL path."""
    path = urlparse(url).path
    ext = Path(path).suffix
    return ext if ext else ".jpg"


class TokenBucketLimiter:
    """Proactive token-bucket rate limiter with 429 deduplication and circuit breaker.

    acquire() is the single pacing gate — call it before every HTTP request.
    signal_429() deduplicates concurrent workers: multiple calls within 1s count
    as one rate-limit event, preventing artificial counter inflation.
    After _CIRCUIT_THRESHOLD distinct events the circuit opens; a single canary
    request is sent after _CIRCUIT_RESET seconds to test recovery.
    """

    def __init__(self, rate: float = 0.5, burst: int = 1) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens: float = float(burst)
        self._last_refill: float = 0.0
        self._pause_until: float = 0.0
        self._consecutive_429s: int = 0
        self._last_429_time: float = -999.0  # loop.time() of last counted event
        self._circuit_open: bool = False
        self._canary_in_flight: bool = False

    async def acquire(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            now = loop.time()

            # --- Circuit open: wait for reset, then allow one canary through ---
            if self._circuit_open:
                if now < self._pause_until:
                    await asyncio.sleep(min(self._pause_until - now, 5.0))
                    continue
                if self._canary_in_flight:
                    # Another worker is already the canary; keep waiting
                    await asyncio.sleep(1.0)
                    continue
                self._canary_in_flight = True
                _console.print("[yellow]Circuit half-open — sending canary request[/yellow]")
                return

            # --- Normal: wait out any 429 backoff pause, then token bucket ---
            if self._pause_until > now:
                await asyncio.sleep(self._pause_until - now)
                # Reset bucket after pause — avoid burst flood when multiple
                # workers wake together
                now = loop.time()
                self._tokens = 0.0
                self._last_refill = now
                continue
            elapsed = now - self._last_refill
            self._tokens = min(float(self._burst), self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            await asyncio.sleep((1.0 - self._tokens) / self._rate)

    def signal_429(self, delay: float) -> None:
        """Record a rate-limit response.

        Multiple concurrent workers hitting 429 in the same burst are
        deduplicated: only the first call within a 1-second window increments
        the event counter, preventing the backoff from escalating 3× faster
        than intended with concurrency=3.
        """
        loop = asyncio.get_running_loop()
        now = loop.time()

        if self._circuit_open:
            # Canary request failed — clear canary flag, extend pause
            self._canary_in_flight = False
            extra = _CIRCUIT_RESET * (2 ** min(self._consecutive_429s - _CIRCUIT_THRESHOLD, 2))
            self._pause_until = max(self._pause_until, now + extra)
            _console.print(
                f"[bold red]Canary failed — circuit stays open, "
                f"next retry in {extra:.0f}s[/bold red]"
            )
            return

        # Only count as a new rate-limit event if >1s since the last one
        if now - self._last_429_time > 1.0:
            self._consecutive_429s += 1
            self._last_429_time = now
            backoff = delay * (2 ** min(self._consecutive_429s - 1, 4))
            jittered = backoff + random.uniform(0.0, backoff * 0.2)
            self._pause_until = max(self._pause_until, now + jittered)
            _console.print(
                f"[yellow]429 rate-limited (event {self._consecutive_429s}) "
                f"— pausing ~{backoff:.0f}s[/yellow]"
            )
            if self._consecutive_429s >= _CIRCUIT_THRESHOLD:
                self._circuit_open = True
                self._canary_in_flight = False
                self._pause_until = max(self._pause_until, now + _CIRCUIT_RESET)
                _console.print(
                    f"[bold red]Circuit OPEN after {self._consecutive_429s} "
                    f"rate-limit events — waiting {_CIRCUIT_RESET:.0f}s[/bold red]"
                )

    def signal_success(self) -> None:
        if self._circuit_open:
            _console.print("[bold green]Circuit CLOSED — rate limit lifted[/bold green]")
            self._circuit_open = False
            self._canary_in_flight = False
        self._consecutive_429s = 0
        self._last_429_time = -999.0


async def _download_one(
    photo: PhotoRecord,
    client: httpx.AsyncClient,
    limiter: TokenBucketLimiter,
    dest_dir: Path,
    progress: Progress,
    task: object,
) -> PhotoRecord:
    """Download a single photo, retrying on transient errors."""
    url = _get_download_url(photo)
    if url is None:
        progress.advance(task)
        return photo

    ext = _get_extension(url)
    filename = f"{photo.photo_id}{ext}"
    filepath = dest_dir / filename

    if filepath.exists() and filepath.stat().st_size > 0:
        progress.advance(task)
        return photo.model_copy(update={"local_filename": filename})

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        await limiter.acquire()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            limiter.signal_success()
            progress.advance(task)
            return photo.model_copy(update={"local_filename": filename})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else _BASE_429_DELAY
                limiter.signal_429(delay)
                last_exc = exc
                continue
            if exc.response.status_code in range(500, 600) and attempt < _MAX_ATTEMPTS - 1:
                last_exc = exc
                await asyncio.sleep(_BASE_5XX_DELAY * 2 ** min(attempt, 4))
                continue
            last_exc = exc
            break
        except httpx.TimeoutException as exc:
            if attempt < _MAX_ATTEMPTS - 1:
                last_exc = exc
                await asyncio.sleep(_BASE_5XX_DELAY * 2 ** min(attempt, 4))
                continue
            last_exc = exc
            break
        except httpx.HTTPError as exc:
            last_exc = exc
            break

    _console.print(f"[bold red]Download failed[/bold red] photo {photo.photo_id}: {last_exc}")
    progress.advance(task)
    return photo


async def download_photos(
    photos: list[PhotoRecord],
    dest_dir: Path,
    concurrency: int = 1,
    rate: float = 0.5,
) -> list[PhotoRecord]:
    """Download photos concurrently, returning updated PhotoRecords with local_filename set."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    limiter = TokenBucketLimiter(rate=rate, burst=concurrency)
    results: list[PhotoRecord | None] = [None] * len(photos)
    queue: asyncio.Queue = asyncio.Queue()

    for i, photo in enumerate(photos):
        await queue.put((i, photo))
    for _ in range(concurrency):
        await queue.put(None)  # sentinels to stop workers

    progress = Progress(
        TextColumn("[bold blue]Downloading"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    )

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        with progress:
            task = progress.add_task("Photos", total=len(photos))

            async def worker() -> None:
                while True:
                    item = await queue.get()
                    if item is None:
                        queue.task_done()
                        return
                    idx, photo = item
                    results[idx] = await _download_one(photo, client, limiter, dest_dir, progress, task)
                    queue.task_done()

            await asyncio.gather(*[worker() for _ in range(concurrency)])

    return [r if r is not None else photos[i] for i, r in enumerate(results)]
