"""
Root conftest.py — adds the project root to sys.path so pytest can find
simulation/ and processing/ packages whether invoked as `pytest` or `python -m pytest`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
