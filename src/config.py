"""Configuration for kindle2md."""
from pathlib import Path


# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default directories
INBOX_DIR = PROJECT_ROOT / "inbox"
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

# Default Claude model
DEFAULT_MODEL = "sonnet"
