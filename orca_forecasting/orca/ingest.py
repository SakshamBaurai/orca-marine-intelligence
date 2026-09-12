"""Memory-efficient ingestion.

Two responsibilities, both strictly streaming:

1. ``cast_csv_to_parquet`` — convert the original multi-gigabyte CSV export into a
   compact, dictionary/float32-encoded Parquet **without ever holding the whole
   frame in RAM**.  This is the one-time bridge from the raw 13M+ row export to
   the format the pipeline actually uses.

2. ``iter_clean_surface_batches`` — the single reader used everywhere else.  It
   projects only the needed columns, filters to the configured depth layer,
   drops rows with missing physical variables, casts to float32, and yields
   pandas chunks.  Peak memory is bounded by ``chunk_rows`` regardless of total
   dataset size, so 13M or 130M rows read the same way.

Crucially, this module computes **no global statistics** (no global means, no
global scalers, no global imputation).  Missing values are simply dropped per
row (land / cloud gaps), exactly as physical validity requires.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from .config import DataConfig
from .schema import ID_COLUMNS, RAW_FEATURES, load_columns, raw_arrow_schema


def cast_csv_to_parquet(
    csv_path: str | Path,
    parquet_path: str | Path,
    data_cfg: Optional[DataConfig] = None,
    row_group_size: int = 250_000,
    compression: str = "snappy",
) -> dict:
    """Stream a large CSV into a compact Parquet file.

    Uses Arrow's chunked CSV reader + a streaming Parquet writer so memory stays
    flat.  All measurement columns are stored as float32 and ``depth_bin`` is
    dictionary-encoded.

    Returns a small summary dict (rows written, output path, bytes).
    """
    data_cfg = data_cfg or DataConfig()
    csv_path = Path(csv_path)
    parquet_path = Path(parquet_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    target_schema = raw_arrow_schema()
    keep = load_columns(data_cfg.depth_column)

    # Explicit column dtypes for the CSV reader (float32 for measurements).
    convert_options = pacsv.ConvertOptions(
        column_types={
            "latitude": pa.float32(),
            "longitude": pa.float32(),
            **{c: pa.float32() for c in RAW_FEATURES},
            data_cfg.depth_column: pa.string(),
            data_cfg.time_column: pa.string(),
        },
        include_columns=keep,
        # Common CSV spellings of missing values.
        null_values=["", "NaN", "nan", "NA", "null"],
        strings_can_be_null=True,
    )
    read_options = pacsv.ReadOptions(block_size=64 << 20)  # 64 MB blocks

    rows = 0
    writer: Optional[pq.ParquetWriter] = None
    try:
        with pacsv.open_csv(
            csv_path, read_options=read_options, convert_options=convert_options
        ) as reader:
            for record_batch in reader:
                if record_batch.num_rows == 0:
                    continue
                tbl = pa.Table.from_batches([record_batch])
                # Re-order / cast to the canonical schema (dictionary-encode depth).
                tbl = tbl.select(keep)
                tbl = tbl.cast(_align_schema(target_schema, tbl.schema))
                if writer is None:
                    writer = pq.ParquetWriter(
                        parquet_path, tbl.schema, compression=compression
                    )
                writer.write_table(tbl, row_group_size=row_group_size)
                rows += tbl.num_rows
    finally:
        if writer is not None:
            writer.close()

    return {
        "rows_written": rows,
        "output": str(parquet_path),
        "bytes": parquet_path.stat().st_size if parquet_path.exists() else 0,
    }


def _align_schema(target: pa.Schema, present: pa.Schema) -> pa.Schema:
    """Build a cast target that keeps only fields present in ``present``.

    Guards against a source CSV that lacks the dictionary encoding or has a
    slightly different field order.
    """
    fields = []
    present_names = set(present.names)
    for f in target:
        if f.name in present_names:
            fields.append(f)
    return pa.schema(fields)


def iter_clean_surface_batches(
    parquet_path: str | Path,
    data_cfg: Optional[DataConfig] = None,
    columns: Optional[List[str]] = None,
) -> Iterator[pd.DataFrame]:
    """Yield clean, float32, surface-layer chunks — the canonical reader.

    - projects only required columns
    - filters to ``surface_layer`` when configured
    - drops rows missing any raw physical feature (land / cloud gaps)
    - parses ``time`` to datetime

    No batch is retained after it is yielded, so total memory is O(chunk_rows).
    """
    data_cfg = data_cfg or DataConfig()
    parquet_path = Path(parquet_path)
    if not parquet_path.exists():
        raise FileNotFoundError(f"Processed Parquet not found: {parquet_path}")

    read_columns = columns or load_columns(data_cfg.depth_column)
    pf = pq.ParquetFile(parquet_path)

    for record_batch in pf.iter_batches(
        batch_size=data_cfg.chunk_rows, columns=read_columns
    ):
        raw = record_batch.to_pandas()

        # Depth-layer filter (skip entirely if not configured / column absent).
        if data_cfg.surface_layer is not None and data_cfg.depth_column in raw.columns:
            raw = raw.loc[raw[data_cfg.depth_column].astype("string").eq(data_cfg.surface_layer)]

        raw = _filter_to_configured_bounds(raw, data_cfg)
        if raw.empty:
            continue

        present_features = [c for c in RAW_FEATURES if c in raw.columns]
        keep_cols = [c for c in (ID_COLUMNS + present_features) if c in raw.columns]
        clean = raw[keep_cols].dropna(subset=present_features).copy()
        if clean.empty:
            continue

        # Compact numeric dtypes.
        for c in present_features + ["latitude", "longitude"]:
            if c in clean.columns:
                clean[c] = clean[c].astype("float32")

        clean[data_cfg.time_column] = pd.to_datetime(
            clean[data_cfg.time_column], format=data_cfg.time_format, errors="raise"
        )
        yield clean.reset_index(drop=True)


def _filter_to_configured_bounds(df: pd.DataFrame, data_cfg: DataConfig) -> pd.DataFrame:
    """Apply the optional inclusive deployment bounding box to a raw frame."""
    values = (data_cfg.lat_min, data_cfg.lat_max, data_cfg.lon_min, data_cfg.lon_max)
    if all(v is None for v in values):
        return df
    if any(v is None for v in values):
        raise ValueError("Configure all of lat_min, lat_max, lon_min and lon_max, or none of them.")
    if data_cfg.lat_min > data_cfg.lat_max or data_cfg.lon_min > data_cfg.lon_max:
        raise ValueError("Configured geographic bounds have a minimum greater than its maximum.")
    return df.loc[
        df[data_cfg.lat_column].between(data_cfg.lat_min, data_cfg.lat_max)
        & df[data_cfg.lon_column].between(data_cfg.lon_min, data_cfg.lon_max)
    ]


def scan_time_axis(
    parquet_path: str | Path, data_cfg: Optional[DataConfig] = None
) -> np.ndarray:
    """Return the sorted unique timestamps present in the (clean) dataset.

    Streams the ``time`` column only, so it is cheap even on huge files.  Used to
    derive temporal split boundaries without loading feature columns.
    """
    data_cfg = data_cfg or DataConfig()
    cols = [data_cfg.time_column]
    if data_cfg.surface_layer is not None:
        cols = [data_cfg.depth_column, data_cfg.time_column]
    if any(v is not None for v in (data_cfg.lat_min, data_cfg.lat_max, data_cfg.lon_min, data_cfg.lon_max)):
        cols = list(dict.fromkeys([*cols, data_cfg.lat_column, data_cfg.lon_column]))

    pf = pq.ParquetFile(Path(parquet_path))
    uniques: set = set()
    for record_batch in pf.iter_batches(batch_size=data_cfg.chunk_rows, columns=cols):
        df = record_batch.to_pandas()
        if data_cfg.surface_layer is not None and data_cfg.depth_column in df.columns:
            df = df.loc[df[data_cfg.depth_column].astype("string").eq(data_cfg.surface_layer)]
        df = _filter_to_configured_bounds(df, data_cfg)
        t = pd.to_datetime(
            df[data_cfg.time_column], format=data_cfg.time_format, errors="coerce"
        ).dropna()
        uniques.update(t.unique().tolist())

    return np.array(sorted(pd.to_datetime(list(uniques))), dtype="datetime64[ns]")
