"""ORCA FastAPI serving package."""

from __future__ import annotations

__all__ = ["app"]


def __getattr__(name):
    # Lazy import so `import service` doesn't require FastAPI unless the app is used.
    if name == "app":
        from .app import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
