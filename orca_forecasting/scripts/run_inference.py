"""Batch inference: stream a processed Parquet through a trained bundle.

Scores every clean surface row in ``source_parquet`` and writes the predictions
as Parquet **without materializing the whole dataset** — one row-group in, one
prediction part out.  Peak memory stays at ``chunk_rows`` regardless of dataset
size, mirroring training.

Usage
-----
    python -m scripts.run_inference --config configs/default.yaml
    python -m scripts.run_inference --config configs/default.yaml \
        --source other.parquet --artifacts artifacts --out preds_parquet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from orca.config import Config
from orca.inference import InferenceEngine
from orca.ingest import iter_clean_surface_batches


def run(config_path: str | None, source: str | None, artifacts: str | None, out: str | None) -> dict:
    cfg = Config.load(config_path) if config_path else Config()
    source_parquet = source or cfg.data.source_parquet
    if not source_parquet:
        raise SystemExit("No source parquet given (config.data.source_parquet or --source).")
    artifact_dir = artifacts or cfg.paths.artifact_dir
    out_dir = Path(out or cfg.paths.prediction_dir)
    # Decide single-file vs. directory-of-parts BEFORE creating anything, so a
    # ``--out preds.parquet`` never gets mistakenly created as a directory.
    single_file = out_dir.suffix.lower() == ".parquet"
    (out_dir.parent if single_file else out_dir).mkdir(parents=True, exist_ok=True)

    engine = InferenceEngine.from_dir(artifact_dir, prefer_onnx=cfg.onnx.enable, data_cfg=cfg.data)

    total_rows = 0
    total_alerts = 0
    n_parts = 0
    writer: pq.ParquetWriter | None = None
    try:
        for i, chunk in enumerate(iter_clean_surface_batches(source_parquet, cfg.data)):
            scored = engine.score_frame(chunk)
            total_rows += len(scored)
            total_alerts += int(scored["is_anomaly"].sum())

            table = pa.Table.from_pandas(scored, preserve_index=False)
            if single_file:
                if writer is None:
                    writer = pq.ParquetWriter(out_dir, table.schema, compression="snappy")
                writer.write_table(table)
            else:
                part = out_dir / f"predictions_part_{i:05d}.parquet"
                pq.write_table(table, part, compression="snappy")
            n_parts += 1
    finally:
        if writer is not None:
            writer.close()

    summary = {
        "source": str(source_parquet),
        "artifacts": str(artifact_dir),
        "output": str(out_dir),
        "backend": engine.backend,
        "rows_scored": total_rows,
        "alerts": total_alerts,
        "alert_rate": (total_alerts / total_rows) if total_rows else None,
        "threshold": engine.threshold,
        "parts_written": n_parts,
    }
    (out_dir if out_dir.is_dir() else out_dir.parent).joinpath("inference_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="ORCA streaming batch inference.")
    p.add_argument("--config", default=None, help="Path to a YAML config.")
    p.add_argument("--source", default=None, help="Override source Parquet path.")
    p.add_argument("--artifacts", default=None, help="Override artifact directory.")
    p.add_argument("--out", default=None, help="Output dir (or a *.parquet file).")
    args = p.parse_args()
    summary = run(args.config, args.source, args.artifacts, args.out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
