"""Train the ORCA detector and write a serving bundle.

Thin CLI wrapper around :func:`orca.train.train`.  All behaviour is driven by the
YAML config so the same command works for a regional prototype or a global grid.

Usage
-----
    python -m scripts.run_training --config configs/default.yaml
    python -m scripts.run_training --config configs/default.yaml --no-cv
    python -m scripts.run_training --source my.parquet --artifacts artifacts
"""

from __future__ import annotations

import argparse
import json

from orca.config import Config
from orca.train import train


def main() -> None:
    p = argparse.ArgumentParser(description="Train the ORCA anomaly detector.")
    p.add_argument("--config", default=None, help="Path to a YAML config.")
    p.add_argument("--source", default=None, help="Override source Parquet path.")
    p.add_argument("--artifacts", default=None, help="Override artifact output directory.")
    p.add_argument("--no-cv", action="store_true", help="Skip spatio-temporal cross-validation.")
    args = p.parse_args()

    cfg = Config.load(args.config) if args.config else Config()
    if args.source:
        cfg.data.source_parquet = args.source
    if args.artifacts:
        cfg.paths.artifact_dir = args.artifacts

    result = train(cfg, run_cv=not args.no_cv)
    print(json.dumps({
        "artifact_dir": result.artifact_dir,
        "threshold": result.threshold,
        "boundaries": result.boundaries,
        "calibration": result.calibration,
        "evaluation": result.evaluation,
        "cv_report": (result.cv_report or {}).get("status") if result.cv_report else None,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
