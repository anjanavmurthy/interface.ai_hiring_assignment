"""Make the submission package (solution/kb) and the scorer's contract importable in tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "solution"), str(ROOT / "harness")]
