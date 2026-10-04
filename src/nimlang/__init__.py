"""nimlang: a Nim toolchain for Python projects.

The Nim compiler is shipped inside platform wheels (see ``scripts/make_wheels.py``)
and C compilation is delegated to ``zig cc`` from the ``ziglang`` wheel, so a
working Nim setup needs nothing but ``uv add nimlang``.
"""

from nimlang._toolchain import (
    NimlangError,
    cc_args,
    nim_exe,
    nim_home,
    nimble_exe,
    zig_exe,
    zigcc_shim,
)

__version__ = "0.0.1"

__all__ = [
    "NimlangError",
    "cc_args",
    "nim_exe",
    "nim_home",
    "nimble_exe",
    "zig_exe",
    "zigcc_shim",
]
