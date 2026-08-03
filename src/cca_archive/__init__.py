"""CCA Exhibitions Flickr Archive tool."""

# Load .env file early so environment variables (including DYLD_FALLBACK_LIBRARY_PATH
# for macOS libvips) are available before any modules import pyvips
from dotenv import load_dotenv

load_dotenv()
