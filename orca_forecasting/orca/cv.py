"""Spatio-temporal cross-validation.

Random k-fold is invalid for gridded space-time data: neighbouring rows in space
and time are highly correlated, so a random split leaks almost-identical
observations into both train and validation and massively overstates performance.

This module provides a splitter that blocks along **both** axes:

* **Temporal blocking (forward-chaining)** — validation windows always lie in the
  future relative to their training window, mirroring real deployment where you
  predict forward in time.  ``expanding`` grows the training window each fold;
  ``rolling`` keeps it a fixed size.
* **Spatial blocking (optional)** — validation is restricted to a held-out band of
  longitudes while training excludes that band, testing geographic
  generalization to unseen regions.

The splitter only yields index arrays; the training orchestrator refits the
climatology and model on each fold's *training rows only*, so the whole CV loop
is leak-free end to end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import CVConfig


@dataclass
class SpatioTemporalBlockCV:
    n_temporal_folds: int = 4
    scheme: str = "expanding"          # "expanding" | "rolling"
    min_train_fraction: float = 0.3
    spatial_blocking: bool = False
    n_spatial_blocks: int = 4
    time_column: str = "time"
    lon_column: str = "longitude"

    @classmethod
    def from_config(cls, cfg: CVConfig, time_column="time", lon_column="longitude") -> "SpatioTemporalBlockCV":
        return cls(
            n_temporal_folds=cfg.n_temporal_folds,
            scheme=cfg.scheme,
            min_train_fraction=cfg.min_train_fraction,
            spatial_blocking=cfg.spatial_blocking,
            n_spatial_blocks=cfg.n_spatial_blocks,
            time_column=time_column,
            lon_column=lon_column,
        )

    # ------------------------------------------------------------------ #
    def _temporal_windows(self, unique_times: np.ndarray) -> List[Tuple[int, int, int]]:
        """Return (train_lo, val_lo, val_hi) index triples over the unique-time axis."""
        n = len(unique_times)
        start = int(round(self.min_train_fraction * n))
        start = max(1, min(start, n - self.n_temporal_folds))
        remaining = n - start
        if remaining < self.n_temporal_folds:
            raise ValueError(
                "Not enough distinct timestamps for the requested number of temporal folds."
            )
        edges = np.linspace(start, n, self.n_temporal_folds + 1).astype(int)
        windows = []
        train_len = start  # fixed window length for the rolling scheme
        for i in range(self.n_temporal_folds):
            val_lo, val_hi = edges[i], edges[i + 1]
            if val_hi <= val_lo:
                continue
            train_lo = 0 if self.scheme == "expanding" else max(0, val_lo - train_len)
            windows.append((train_lo, val_lo, val_hi))
        return windows

    def _spatial_blocks(self, df: pd.DataFrame) -> np.ndarray:
        """Assign each row to a longitude-quantile block (geography-agnostic)."""
        lon = df[self.lon_column].to_numpy()
        # Quantile edges -> roughly balanced blocks regardless of extent.
        qs = np.linspace(0, 1, self.n_spatial_blocks + 1)
        edges = np.quantile(lon, qs)
        edges[0] -= 1e-6
        edges[-1] += 1e-6
        return np.clip(np.digitize(lon, edges[1:-1]), 0, self.n_spatial_blocks - 1)

    def split(self, df: pd.DataFrame) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        """Yield (train_positions, val_positions) for each fold."""
        times = pd.to_datetime(df[self.time_column]).to_numpy()
        unique_times = np.array(sorted(pd.unique(times)))
        windows = self._temporal_windows(unique_times)
        blocks = self._spatial_blocks(df) if self.spatial_blocking else None

        for (train_lo, val_lo, val_hi) in windows:
            train_times = unique_times[train_lo:val_lo]
            val_times = unique_times[val_lo:val_hi]
            train_time_mask = np.isin(times, train_times)
            val_time_mask = np.isin(times, val_times)

            if blocks is None:
                yield from _emit(train_time_mask, val_time_mask)
            else:
                for b in range(self.n_spatial_blocks):
                    tr = train_time_mask & (blocks != b)
                    va = val_time_mask & (blocks == b)
                    yield from _emit(tr, va)

    def get_n_splits(self, df: Optional[pd.DataFrame] = None) -> int:
        base = self.n_temporal_folds
        return base * self.n_spatial_blocks if self.spatial_blocking else base


def _emit(train_mask: np.ndarray, val_mask: np.ndarray):
    tr = np.where(train_mask)[0]
    va = np.where(val_mask)[0]
    if len(tr) and len(va):
        yield tr, va


# --------------------------------------------------------------------------- #
# Drift / stability diagnostic
# --------------------------------------------------------------------------- #
def population_stability_index(
    expected: np.ndarray, actual: np.ndarray, bins: int = 10, eps: float = 1e-6
) -> float:
    """PSI between two score distributions.

    <0.1 negligible drift, 0.1-0.25 moderate, >0.25 significant.  Used to flag
    folds where the validation score distribution departs sharply from training —
    a sign of overfitting or non-stationarity.
    """
    expected = np.asarray(expected, dtype="float64")
    actual = np.asarray(actual, dtype="float64")
    if expected.size == 0 or actual.size == 0:
        return float("nan")
    quantiles = np.linspace(0, 1, bins + 1)
    edges = np.unique(np.quantile(expected, quantiles))
    if edges.size < 2:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    e_hist, _ = np.histogram(expected, bins=edges)
    a_hist, _ = np.histogram(actual, bins=edges)
    e_prop = np.clip(e_hist / max(e_hist.sum(), 1), eps, None)
    a_prop = np.clip(a_hist / max(a_hist.sum(), 1), eps, None)
    return float(np.sum((a_prop - e_prop) * np.log(a_prop / e_prop)))
