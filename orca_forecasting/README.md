# ORCA — Marine Oceanographic Anomaly Detection

A leak-free, memory-efficient, API-ready pipeline for detecting anomalies in
gridded ocean/atmosphere fields (temperature, salinity, currents, chlorophyll,
sea-level anomaly, winds). It is the production refactor of an exploratory
research notebook (`mainmodel.ipynb`) into a modular Python package that trains a
regularized Isolation-Forest detector and serves it statelessly behind a REST
API.

The package was built around five hard requirements, and the sections below
explain exactly where each is enforced in code.

---

## Why this exists (notebook → package)

The original notebook produced a workable model but had three properties that make
it unsafe to ship:

- It computed a **global** daily-mean baseline with `df.groupby('time').transform('mean')`
  and a **global** scaler — both fit over *all* rows, including the data used to
  evaluate the model. That is textbook data leakage.
- It loaded the full multi-million-row frame into memory as float64.
- Its logic was entangled in one notebook with hardcoded regional assumptions, so
  it could neither be unit-tested nor served.

This package keeps the modelling idea (unsupervised anomaly detection on
standardized ocean anomalies) but rebuilds the machinery so it is leak-free,
streams within a bounded memory budget, and exposes a clean training/serving
boundary.

---

## The five mandates and how they are satisfied

### 1. Zero data leakage

Leakage is prevented structurally, not by convention.

- **Temporal blocking first.** `orca/splits.py` derives `train | calibration | test`
  boundaries on the *sorted unique time axis* (not row counts), so every
  timestamp's entire spatial grid lands in exactly one block.
- **Climatology fit on the training block only.** `orca/climatology.py` replaces
  the notebook's global `groupby('time').transform('mean')` with a per-spatial-cell,
  per-season climatology accumulated **only from rows strictly earlier than the
  calibration boundary** (`fit_climatology(..., train_end_exclusive=calib_start)`).
  Test rows can never influence the baseline.
- **No global scaler.** Because anomalies are standardized *locally* by each cell's
  own training standard deviation, the engineered anomaly features are already
  z-scores. The only scaler (`RobustScaler`) lives *inside* the sklearn pipeline
  and is therefore fit on the training pool only (`orca/model.py`, `orca/train.py`).
- **Threshold calibrated on a held-out calibration block**, never on train or test
  (`orca/train.py` step 4).
- **Test block used once, for reporting only.**

This is verified mechanically in `tests/test_leakage.py`: it corrupts every
calibration+test row, refits, and asserts the climatology is **byte-identical**,
with a positive control that corrupting training rows *does* change it.

### 2. Overfitting mitigation

- **Spatio-temporal cross-validation** (`orca/cv.py`): forward-chaining
  (expanding) or rolling temporal folds, optional longitude-quantile spatial
  blocking so validation cells are geographically disjoint from training cells.
  The climatology and model are **refit per fold on that fold's training rows
  only** (`orca/train.cross_validate`), so CV is itself leak-free.
- **Regularization is explicit and lives in config**: bounded `max_samples` per
  tree (a strong regularizer that also caps fit time and prevents anomaly
  "masking"), `max_features < 1.0` to decorrelate trees, a moderate
  `n_estimators`, and a **calibrated operating threshold** instead of a guessed
  `contamination`.
- **PSI (Population Stability Index)** between fold train/val score distributions
  flags instability/non-stationarity.

### 3. Extreme memory efficiency

- **Everything streams.** `orca/ingest.py` reads Parquet in bounded batches
  (`pyarrow` `iter_batches`, `chunk_rows`), projects only required columns, filters
  to the surface layer, drops rows with missing physical variables, and casts to
  **float32**. Peak RAM is O(`chunk_rows`), independent of dataset size — 3M or
  300M rows read the same way.
- **The climatology is a streaming accumulator** (per-bucket sum, sum-of-squares,
  count), so memory scales with occupied cells, not rows.
- **Bounded training pool.** The model is fit on a randomly sub-sampled pool drawn
  from the training block (`train_pool_target`), never the full frame.
- **float32 / dictionary-encoded Parquet.** `cast_csv_to_parquet` streams the
  original multi-GB CSV into a compact Parquet with Arrow, never holding the whole
  frame in memory.
- No 13M-row float64 frame is ever materialized.

### 4. Modular & API-ready

- The pipeline decomposes into single-responsibility modules (see layout below),
  each independently unit-tested.
- Training produces a **self-contained, versioned artifact bundle**
  (`orca/artifacts.py`): climatology + sklearn pipeline + optional ONNX graph +
  `metadata.json` (feature order, threshold, provenance, data extent).
- Inference is a **stateless engine** (`orca/inference.py`): it loads a bundle once
  and scores one record or a million through the *same* pure `build_features` path
  used in training — no per-request fitting, no cross-row aggregation.
- A **FastAPI microservice** (`service/app.py`) exposes `/health`, `/metadata`,
  `/predict`, `/predict/batch`, and (when configured) `/predict/live`.
- **ONNX export** (`orca/onnx_export.py`) is validated for numerical parity at
  training time; the engine transparently applies the `score_samples` affine offset
  so ONNX and joblib scores match.

### 5. Geographic generalizability

- **No hardcoded coordinates, basins, or grid extents** anywhere in the logic.
  Spatial cells are arithmetic (`floor(coord / cell_size)`), valid for any
  latitude/longitude.
- Cell **areas use spherical geometry** (cos-latitude, `EARTH_RADIUS_KM = 6371.0088`),
  so per-pixel area is correct anywhere on the globe (`orca/geo.py`).
- Grid spacing, spatial bounds, and per-pixel area are **inferred from the data** at
  run time when not configured.
- A **hierarchical climatology fallback** (cell → latitude band → season-global →
  global) keeps the baseline defined for sparse cells and previously unseen
  regions, which is what lets the same artifact generalize from a regional basin to
  a global grid.

---

## Package layout

```
orca_forecasting/
├── orca/                     # the library
│   ├── config.py             # declarative dataclass config (YAML-loadable, no hardcoded geo)
│   ├── schema.py             # column + ordered feature contract, Arrow schema
│   ├── geo.py                # spatial cells, lat bands, seasons, spherical area, grid inference
│   ├── ingest.py             # streaming float32 Parquet reader + CSV→Parquet caster
│   ├── splits.py             # temporal train/calibration/test blocking
│   ├── climatology.py        # leak-free per-cell/season z-score baseline (streaming)
│   ├── features.py           # pure raw-chunk → ordered model-feature matrix
│   ├── cv.py                 # spatio-temporal blocked CV + PSI
│   ├── model.py              # RobustScaler + regularized IsolationForest + threshold
│   ├── train.py              # orchestrator: blocks → clim → fit → calibrate → eval → bundle
│   ├── artifacts.py          # versioned bundle save/load
│   ├── onnx_export.py        # ONNX export with parity check + score offset
│   ├── inference.py          # stateless scoring engine (ONNX or joblib)
│   ├── analytics.py          # optional heuristic marine-health index + ecological states
│   ├── events.py             # optional offline DBSCAN spatial event clustering
│   └── synth.py              # schema-accurate synthetic data (used by tests)
├── service/                  # FastAPI app + Pydantic models
├── scripts/                  # CLI wrappers: orca-convert / orca-train / orca-infer
├── tests/                    # pytest suite (leakage, features, CV, API, ...)
├── configs/default.yaml      # example config (points at the processed Parquet)
├── pyproject.toml
└── requirements.txt
```

---

## Installation

Requires Python ≥ 3.10.

```bash
cd orca_forecasting
pip install -e .              # core: numpy, pandas, pyarrow, scikit-learn, joblib, pyyaml
pip install -e ".[service]"   # + FastAPI / uvicorn / pydantic (to run the API)
pip install -e ".[onnx]"      # + skl2onnx / onnx / onnxruntime (portable export)
pip install -e ".[dev]"       # + pytest / httpx (to run the tests)
```

Everything except the core dependencies is optional; the pipeline trains and
scores with the core set alone (ONNX simply won't be exported, and the service
won't start).

---

## Data

The pipeline reads a **processed Parquet**. The bundled config points at:

```
orca_processed_ocean_data.parquet
```

Expected columns (renameable via config):

| column | meaning |
|---|---|
| `time` | observation date (default parsed as `%Y-%m-%d`) |
| `latitude`, `longitude` | grid coordinates |
| `depth_bin` | depth layer label; the pipeline keeps `surface_layer` (default `"0-50m"`) |
| `thetao`, `so`, `uo`, `vo`, `chl`, `sla`, `u10`, `v10` | required physical variables |

Rows missing any required physical variable are dropped per row (land/cloud gaps);
no global imputation is performed.

If you still have the original multi-gigabyte CSV export, cast it once:

```bash
python -m scripts.convert_csv_to_parquet --csv raw_export.csv --parquet orca_processed_ocean_data.parquet
# or, with paths in the config:
python -m scripts.convert_csv_to_parquet --config configs/default.yaml
```

---

## Usage

### Train

```bash
python -m scripts.run_training --config configs/default.yaml
python -m scripts.run_training --config configs/default.yaml --no-cv   # skip cross-validation
```

Or programmatically:

```python
from orca.config import Config
from orca.train import train

cfg = Config.from_yaml("configs/default.yaml")
result = train(cfg, run_cv=True)
print(result.threshold, result.boundaries, result.evaluation)
```

Training writes a bundle to `paths.artifact_dir` (default `artifacts/`) and a
`run_manifest.json` capturing boundaries, calibration, evaluation, CV report, and
ONNX status.

### Batch inference

Streams a Parquet through a trained bundle and writes predictions without
materializing the dataset:

```bash
python -m scripts.run_inference --config configs/default.yaml                       # directory of parts
python -m scripts.run_inference --config configs/default.yaml --out predictions.parquet   # single file
```

Output columns: the identifier columns (`time`, `latitude`, `longitude`),
`raw_score` (raw `score_samples`; lower = more anomalous), `anomaly_score`
(`-raw_score`; higher = more anomalous), and `is_anomaly` (raw ≤ calibrated
threshold). A sibling `inference_summary.json` records rows scored, alert count,
and backend used.

### Serve (REST API)

```bash
export ORCA_ARTIFACT_DIR=artifacts
export ORCA_CONFIG=configs/default.yaml     # optional
export ORCA_PREFER_ONNX=1                    # 0 to force joblib
uvicorn service.app:app --host 0.0.0.0 --port 8000
```

```
GET  /health          liveness + which backend is loaded
GET  /metadata        feature order, threshold, params, data extent, provenance
GET  /dashboard/telemetry?station=Kochi  display-ready coastal telemetry from the latest forecast parquet
POST /predict         { "observation": { ... } }
POST /predict/batch   { "observations": [ { ... }, ... ] }
POST /predict/live    { "observation_date": "2026-09-10" }  # configured daily provider -> model
```

A `/predict` body supplies one observation with `time`, `latitude`, `longitude`
and the eight physical variables; incomplete records are rejected with HTTP 422.

### Telemetry dashboard

The accompanying browser client is in
`frontend/index.html` (or `public/index.html`). It requests
`/dashboard/telemetry?station=<station>` and renders station-local model health,
PFZ candidates, planning lines, and only the weather fields present in the
forecast artifact. When the frontend is served on localhost port 3000 or 3001 it
uses `http://localhost:8000` automatically; another deployment can set
`window.ORCA_API_BASE` before loading `orca-dashboard.js`.

The adapter reads `latest_forecast_predictions.parquet`, then
`predictions.parquet`, and finally the known legacy output location. In production
set this explicit path before starting Uvicorn:

```powershell
$env:ORCA_DASHBOARD_FORECAST_PATH = "C:/path/to/latest_forecast_predictions.parquet"
uvicorn service.app:app --host 0.0.0.0 --port 8000
```

PFZs combine upper-quartile chlorophyll with upper-quartile local thermal-front
strength. They are decision-support signals, not safe-navigation clearance;
official notices, charts, weather and harbour guidance remain authoritative.

### Live daily comparative inference

The baseline/model is historical and frozen at training time; it is not retrained
on each request.  `/predict/live` fetches the requested daily observations and
compares every point with the artifact's leak-free per-cell seasonal climatology,
then scores it with the fixed detector.  This is the production-safe way to make
a rolling daily comparison without leaking future data into the baseline.

The project ships with the live feed deliberately disabled because no public
provider endpoint or credential was supplied.  It therefore currently performs
**offline batch inference only** until `live` in `configs/default.yaml` is
configured.  Set the Arabian Sea bounding box under `data`, point `live.endpoint`
at an HTTPS JSON endpoint (typically a small Copernicus/INCOIS/NOAA adapter), and
place its credential in the environment variable named by `live.api_key_env`.
The endpoint must return records containing the ORCA canonical fields (`time`,
`latitude`, `longitude`, `thetao`, `so`, `uo`, `vo`, `chl`, `sla`, `u10`, `v10`);
use `live.column_map` for different provider field names.  The service sends the
date and configured bounding-box parameters, rejects records outside the box,
uses retry/timeout controls, and never stores credentials in the config.

### Optional analytics & events

`orca/analytics.py` adds interpretable, **non-ML** overlays — a Marine Health Index
in [0, 1] and ecological-state labels (heatwave / upwelling / eutrophication /
nominal) from the standardized anomalies — and is attached to API responses when
`analytics.enable` is true. `orca/events.py` clusters flagged points offline with
DBSCAN (haversine metric) into spatial events with spherical-area estimates, for
batch reporting.

---

## The artifact bundle

```
artifacts/
├── climatology/          # leak-free baseline: cell/band/season parquet + meta json
├── detector.joblib       # RobustScaler + IsolationForest pipeline (authoritative)
├── detector.onnx         # portable ONNX graph (optional; parity-checked)
├── metadata.json         # feature order, threshold, params, data extent, provenance
└── run_manifest.json     # full training run record
```

joblib is always written and is authoritative; ONNX is an additional portable
export. The serving engine prefers ONNX when present and valid, else falls back to
joblib automatically.

---

## Model feature contract

Feature **order is fixed and persisted** with the bundle so serving never guesses
(`orca/schema.py`). The ten features are four leak-free climatological anomalies
followed by six per-row kinematic/forcing terms:

```
thetao_clim_z, so_clim_z, sla_clim_z, chl_clim_z,
uo, vo, current_speed, u10, v10, wind_speed
```

`current_speed` and `wind_speed` are per-row magnitudes (`hypot`) — no aggregation,
no leakage.

---

## Configuration

All behaviour is driven by `orca/config.py` dataclasses; a YAML file overrides only
the keys it cares about. Notable knobs:

- `climatology.cell_size_deg` — coarsen for global grids, refine for dense regional
  data.
- `climatology.min_cell_count` — samples a `(cell, season)` bucket needs before it's
  trusted (else the fallback hierarchy is used).
- `split.train_end` / `split.test_start` — pin absolute date cutoffs for
  reproducible operational splits; otherwise fractions of the time axis are used.
- `model.max_samples` / `model.max_features` — the primary regularizers.
- `calibration.target_alert_rate` — operational fraction of rows flagged.
- `cv.scheme` (`expanding`/`rolling`), `cv.spatial_blocking`.
- `data.time_format` — defaults to `"%Y-%m-%d"`. **If your processed Parquet stores
  full timestamps** (e.g. `2020-01-01 00:00:00`) rather than plain dates, set this to
  `null` so pandas infers the format; a fixed format is ~10× faster on large frames
  but will error on a mismatch.

---

## Testing

```bash
pip install -e ".[dev,service,onnx]"
pytest
```

The suite is self-contained: it generates a **schema-accurate synthetic dataset**
(`orca/synth.py`) with a known injected anomaly region, so no external data is
needed. Optional-dependency tests (`onnxruntime`, `sklearn` extras, `fastapi`,
`httpx`) are guarded with `importorskip` and skip cleanly when a dependency is
absent. Highlights:

- `test_leakage.py` — future-corruption invariance (+ positive control).
- `test_features.py` — exact feature order/contract, float32, finiteness.
- `test_cv.py` — no fold overlap, forward-chaining, spatial disjointness, PSI.
- `test_inference.py` — engine ↔ pipeline agreement, ONNX/joblib parity, injected-
  anomaly recall.
- `test_api.py` — `/health`, `/metadata` (10-feature contract), predict, batch, 422.
- `test_config.py`, `test_artifacts.py`, `test_ingest.py`, `test_geo.py`,
  `test_analytics.py`, `test_events.py`.

---

## Design notes & caveats

- **Scores.** Isolation Forest `score_samples` returns *lower = more anomalous*. The
  raw value is preserved as `raw_score`; `anomaly_score = -raw_score` is exposed as a
  monotonic "higher = more severe" convenience.
- **Thresholding is operational, not ground truth.** There are no anomaly labels;
  the threshold is a calibrated quantile of held-out scores and should be tuned to
  the alert budget you can action.
- **Chlorophyll is `log1p`-transformed** before climatology (right-skewed). Inputs
  are expected to be physically non-negative; strongly negative artifacts (< −1)
  would produce non-finite transforms and should be cleaned upstream.
- **ONNX is best-effort.** If export or the parity check fails, training still
  succeeds and joblib remains authoritative.
