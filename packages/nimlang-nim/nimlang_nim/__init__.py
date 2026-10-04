"""The Nim compiler distribution, packaged as a wheel for nimlang.

This package holds no code of its own: it ships ``nim/`` (bin, lib, config) and
tells nimlang where it lives. Its version is the Nim version it contains.
"""

from pathlib import Path

NIM_HOME = Path(__file__).resolve().parent / "nim"
NIM_VERSION = "@NIM_VERSION@"
