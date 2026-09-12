"""One-time bridge: cast the raw multi-gigabyte CSV export to compact Parquet.

Wraps :func:`orca.ingest.cast_csv_to_parquet`, which streams the CSV through
Arrow and writes float32 / dictionary-encoded Parquet without ever holding the
full ~13M-row frame in memory.  Run this once; everything else reads the Parquet.

Usage
-----
    python -m scripts.convert_csv_to_parquet --config configs/default.yaml
    python -m scripts.convert_csv_to_parquet --csv raw.csv --parquet processed.parquet
"""

from __future__ import annotations

import argparse
import json

from orca.config import Config
from orca.ingest import cast_csv_to_parquet


def main() -> None:
    p = argparse.ArgumentParser(description="Cast the raw ORCA CSV export to Parquet.")
    p.add_argument("--config", default=None, help="Path to a YAML config.")
    p.add_argument("--csv", default=None, help="Override source CSV path.")
    p.add_argument("--parquet", default=None, help="Override output Parquet path.")
    p.add_argument("--row-group-size", type=int, default=250_000)
    p.add_argument("--compression", default="snappy")
    args = p.parse_args()

    cfg = Config.load(args.config) if args.config else Config()
    csv_path = args.csv or cfg.data.source_csv
    parquet_path = args.parquet or cfg.data.source_parquet
    if not csv_path or not parquet_path:
        raise SystemExit("Both a source CSV and a target Parquet path are required.")

    summary = cast_csv_to_parquet(
        csv_path, parquet_path, cfg.data,
        row_group_size=args.row_group_size, compression=args.compression,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
