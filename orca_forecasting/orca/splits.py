"""Temporal blocking: derive train / calibration / test boundaries.

Splits are computed on the *sorted unique time axis*, not on row counts, so every
timestamp's spatial grid lands entirely inside one block.  This is the backbone
of the no-leakage guarantee: climatology, scaler, model, and threshold are all
fit on data strictly earlier in time than the data they are evaluated on.

Layout of the timeline (earliest -> latest):

    [ ------- training ------- | -- calibration -- | ------- test ------- ]
                               ^ calib_start        ^ test_start

- training   : fits climatology, scaler, and the Isolation Forest
- calibration: sets the operational alert threshold (never touched by fit)
- test       : held out entirely for final evaluation
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import SplitConfig


@dataclass
class TemporalBoundaries:
    calib_start: pd.Timestamp  # first timestamp of the calibration block
    test_start: pd.Timestamp   # first timestamp of the test block
    t_min: pd.Timestamp
    t_max: pd.Timestamp

    def block_of(self, times: pd.Series) -> pd.Series:
        """Label each timestamp as 'train' / 'calibration' / 'test'."""
        t = pd.to_datetime(times)
        out = np.where(
            t >= self.test_start,
            "test",
            np.where(t >= self.calib_start, "calibration", "train"),
        )
        return pd.Series(out, index=getattr(times, "index", None))

    def to_dict(self) -> dict:
        return {
            "calib_start": str(self.calib_start.date()),
            "test_start": str(self.test_start.date()),
            "t_min": str(self.t_min.date()),
            "t_max": str(self.t_max.date()),
        }


def _time_at_fraction(time_axis: np.ndarray, frac: float) -> pd.Timestamp:
    """Timestamp at fractional position ``frac`` along the sorted unique axis."""
    frac = min(max(frac, 0.0), 1.0)
    idx = int(np.clip(round(frac * (len(time_axis) - 1)), 0, len(time_axis) - 1))
    return pd.Timestamp(time_axis[idx])


def compute_boundaries(time_axis: np.ndarray, cfg: SplitConfig) -> TemporalBoundaries:
    """Compute block boundaries from the unique, sorted time axis.

    Absolute cutoffs in the config take precedence over fractions, so a
    deployment can pin exact dates when it needs reproducible operational splits.
    """
    if len(time_axis) < 3:
        raise ValueError("Need at least 3 distinct timestamps to form temporal blocks.")
    time_axis = np.array(sorted(pd.to_datetime(time_axis)), dtype="datetime64[ns]")
    t_min = pd.Timestamp(time_axis[0])
    t_max = pd.Timestamp(time_axis[-1])

    # ---- test_start ---------------------------------------------------- #
    if cfg.test_start:
        test_start = pd.Timestamp(cfg.test_start)
    elif cfg.train_end:
        test_start = pd.Timestamp(cfg.train_end)
    else:
        test_start = _time_at_fraction(time_axis, 1.0 - cfg.test_fraction)

    # ---- calib_start (within the pre-test "dev" block) ----------------- #
    dev_axis = time_axis[time_axis < np.datetime64(test_start)]
    if len(dev_axis) < 2:
        raise ValueError(
            "Development block (pre-test) is too small; adjust split fractions/dates."
        )
    calib_start = _time_at_fraction(dev_axis, 1.0 - cfg.calibration_fraction)
    # Guarantee a non-empty training block strictly before calibration.
    if calib_start <= t_min:
        calib_start = pd.Timestamp(dev_axis[1])

    return TemporalBoundaries(
        calib_start=calib_start, test_start=test_start, t_min=t_min, t_max=t_max
    )
