"""ORCA — leak-free, memory-efficient marine anomaly detection pipeline.

Public surface is intentionally small; import submodules directly for the rest.
"""

from __future__ import annotations

__version__ = "1.0.0"

from .config import Config  # noqa: E402

__all__ = ["Config", "__version__"]
