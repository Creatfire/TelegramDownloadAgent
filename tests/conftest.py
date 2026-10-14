"""Unit tests run fully offline against a throw-away data directory."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["TGA_DATA_DIR"] = tempfile.mkdtemp(prefix="tga-test-")
os.environ.setdefault("TGA_PORT", "17999")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
