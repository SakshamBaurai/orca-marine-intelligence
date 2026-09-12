"""
ORCA Ocean Intelligence Platform
Unified 24-Hour Forecast Ingestion, Inference & Event Clustering Engine
"""

from datetime import date, timedelta
from pathlib import Path
import tempfile
import warnings
import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import copernicusmarine
import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
import xarray as xr

warnings.filterwarnings("ignore", category=UserWarning)

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent if BASE_DIR.name == "core_scripts" else BASE_DIR

MODEL_DIR = (
    PROJECT_ROOT / "model_artifacts" if (PROJECT_ROOT / "model_artifacts").exists()
    else BASE_DIR / "model_artifacts"
)
DATA_DIR = (
    PROJECT_ROOT / "data" if (PROJECT_ROOT / "data").exists()
    else BASE_DIR / "data"
)

ISO_FOREST_PATH = (
    MODEL_DIR / "orca_isolation_forest.joblib" if (MODEL_DIR / "orca_isolation_forest.joblib").exists()
    else BASE_DIR / "model_artifacts" / "orca_isolation_forest.joblib" if (BASE_DIR / "model_artifacts" / "orca_isolation_forest.joblib").exists()
    else PROJECT_ROOT / "orca_isolation_forest.joblib"
)
ISO_FEATURES_PATH = (
    MODEL_DIR / "orca_features.joblib" if (MODEL_DIR / "orca_features.joblib").exists()
    else BASE_DIR / "model_artifacts" / "orca_features.joblib" if (BASE_DIR / "model_artifacts" / "orca_features.joblib").exists()
    else PROJECT_ROOT / "orca_features.joblib"
)
XGB_MODEL_PATH = MODEL_DIR / "orca_xgboost_regressor.joblib"
XGB_FEATURES_PATH = MODEL_DIR / "orca_xgb_features.joblib"

PREDICTIONS_PARQUET_OUT = PROJECT_ROOT / "latest_forecast_predictions.parquet"
EVENTS_CSV_OUT = PROJECT_ROOT / "latest_forecast_events.csv"

# -------------------------------------------------------------
# Authentication via cred.json
# -------------------------------------------------------------
CRED_PATH = (
    PROJECT_ROOT / "cred.json" if (PROJECT_ROOT / "cred.json").exists()
    else BASE_DIR / "cred.json"
)
CMEMS_USER = None
CMEMS_PASS = None

if CRED_PATH.exists():
    with open(CRED_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    copernicus_creds = data.get("copernicus", data)
    CMEMS_USER = copernicus_creds.get("username")
    CMEMS_PASS = copernicus_creds.get("password")

    if CMEMS_USER and CMEMS_PASS:
        print(f"🔑 Successfully loaded Copernicus credentials for user: {CMEMS_USER}")
    else:
        print("⚠️ Warning: 'username' or 'password' missing in cred.json")
else:
    print(f"⚠️ Warning: {CRED_PATH} not found. Falling back to cached session.")

# Bounding Box: Eastern Arabian Sea & Western Indian Shelf (Full Gujarat to Southern Tip)
BOUNDS = {
    "min_lon": 65.0,
    "max_lon": 77.5,
    "min_lat": 8.0,
    "max_lat": 24.0
}

# Climatological SST reference (°C) by month for the Eastern Arabian Sea
ARABIAN_SEA_SST_CLIMATOLOGY = {
    1: 26.5, 2: 26.8, 3: 27.5, 4: 28.5, 5: 29.5, 6: 28.8,
    7: 28.0, 8: 27.2, 9: 27.4, 10: 28.2, 11: 28.0, 12: 27.0
}

CMEMS_SOURCES = [
    {
        "dataset_id": "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m",
        "variables": ["thetao"],
        "prefix": "thetao",
        "is_forecast": True
    },
    {
        "dataset_id": "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m",
        "variables": ["uo", "vo"],
        "prefix": "cur",
        "is_forecast": True
    },
    {
        "dataset_id": "cmems_mod_glo_phy-so_anfc_0.083deg_P1D-m",
        "variables": ["so"],
        "prefix": "so",
        "is_forecast": True
    },
    {
        "dataset_id": "cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
        "variables": ["CHL"],
        "prefix": "chl",
        "is_forecast": False
    }
]

# ==============================================================================
# PIPELINE STAGES
# ==============================================================================
def download_cmems_forecast(target_date: date, temp_dir: Path) -> dict[str, Path]:
    """Download physical forecast and satellite observation variables into an isolated temporary directory."""
    downloaded_paths = {}

    for source in CMEMS_SOURCES:
        prefix = source["prefix"]
        # Forecast feeds support target_date; satellite NRT L4 products are available up to today - 1 day
        query_date = target_date if source.get("is_forecast", True) else (target_date - timedelta(days=1))
        out_file = temp_dir / f"temp_{prefix}_{query_date.strftime('%Y-%m-%d')}.nc"
        print(f"⬇️  Fetching {source['variables']} from {source['dataset_id']}...")

        success = False
        # Try up to 3 days back if satellite lag is present
        for offset in range(3):
            cur_date = query_date - timedelta(days=offset)
            cur_str = cur_date.strftime("%Y-%m-%d")
            try:
                copernicusmarine.subset(
                    dataset_id=source["dataset_id"],
                    variables=source["variables"],
                    minimum_longitude=BOUNDS["min_lon"],
                    maximum_longitude=BOUNDS["max_lon"],
                    minimum_latitude=BOUNDS["min_lat"],
                    maximum_latitude=BOUNDS["max_lat"],
                    start_datetime=f"{cur_str}T00:00:00",
                    end_datetime=f"{cur_str}T23:59:59",
                    output_filename=str(out_file),
                    overwrite=True,
                    username=CMEMS_USER,
                    password=CMEMS_PASS
                )
                downloaded_paths[prefix] = out_file
                success = True
                print(f"✅ Successfully retrieved {prefix} ({source['dataset_id']}) for {cur_str}.")
                break
            except Exception as err:
                print(f"⚠️ Notice: Attempt for {prefix} on {cur_str} failed: {err}")
                if source.get("is_forecast", True):
                    # Forecast products shouldn't need date walk-back
                    break

        if not success:
            print(f"⚠️ Warning: Could not retrieve {source['dataset_id']}.")

    if not downloaded_paths:
        raise RuntimeError("No forecast feeds were downloaded. Check network connection or CMEMS credentials.")

    return downloaded_paths

def ingest_and_engineer_physics(file_dict: dict[str, Path], target_date: date) -> pd.DataFrame:
    """Load NetCDF datasets safely into memory, interpolate satellite observations, and engineer physical features."""
    physics_keys = [k for k in ["thetao", "cur", "so"] if k in file_dict]
    if not physics_keys:
        raise RuntimeError("No physical ocean datasets available to build grid.")

    loaded_datasets = []
    for k in physics_keys:
        with xr.open_dataset(file_dict[k]) as ds:
            loaded_datasets.append(ds.load())

    merged_ds = xr.merge(loaded_datasets)

    if "depth" in merged_ds.dims:
        merged_ds = merged_ds.isel(depth=0)
    if "time" in merged_ds.dims and merged_ds.dims["time"] > 1:
        merged_ds = merged_ds.isel(time=0)

    # Ingest satellite Chlorophyll ground truth if available
    if "chl" in file_dict:
        try:
            with xr.open_dataset(file_dict["chl"]) as ds_chl:
                chl_loaded = ds_chl.load()
            if "time" in chl_loaded.dims:
                chl_loaded = chl_loaded.isel(time=-1)

            chl_var = "CHL" if "CHL" in chl_loaded.data_vars else ("chl" if "chl" in chl_loaded.data_vars else list(chl_loaded.data_vars.keys())[0])
            chl_interp = chl_loaded[chl_var].interp(
                latitude=merged_ds["latitude"],
                longitude=merged_ds["longitude"],
                method="nearest"
            )
            merged_ds["chl"] = chl_interp
            print("🌿 Successfully mapped Copernicus satellite Chlorophyll-a ground truth onto regional grid.")
        except Exception as e:
            print(f"⚠️ Could not interpolate satellite Chlorophyll: {e}")

    df = merged_ds.to_dataframe().dropna(subset=["thetao"]).reset_index()

    df["time"] = target_date.strftime("%Y-%m-%d")
    df["current_speed"] = (
        np.sqrt(df["uo"] ** 2 + df["vo"] ** 2) if {"uo", "vo"}.issubset(df.columns) else 0.2
    )

    clim_mean = ARABIAN_SEA_SST_CLIMATOLOGY.get(target_date.month, 27.5)
    df["SSTA"] = df["thetao"] - clim_mean
    df["thetao_daily_anomaly"] = df["SSTA"]
    df["sla_anomaly"] = 0.0
    df["sla_daily_anomaly"] = 0.0

    # Physical Salinity from Copernicus
    if "so" not in df.columns:
        df["so"] = 36.0
    df["salinity_anomaly"] = df["so"] - 36.0
    df["so_daily_anomaly"] = df["salinity_anomaly"]

    # Atmospheric & proxy fields
    df["sla"] = 0.0
    df["u10"] = 0.0
    df["v10"] = 0.0
    df["wind_speed"] = 5.0
    df["wind_stress_proxy"] = 0.05

    return df

def estimate_biology_features(df: pd.DataFrame) -> pd.DataFrame:
    """Retain real Copernicus satellite Chlorophyll-a; predict via XGBoost or baseline only if missing."""
    if "chl" in df.columns and df["chl"].dropna().nunique() > 10:
        print("🌱 Retaining live Copernicus satellite Chlorophyll-a ground truth.")
        df["chl"] = np.clip(df["chl"], 0.01, 40.0)
        df["log_chl"] = np.log1p(df["chl"])
        df["chl_sst_ratio"] = df["chl"] / np.maximum(df["thetao"], 1.0)
        return df

    if XGB_MODEL_PATH.exists() and XGB_FEATURES_PATH.exists():
        try:
            xgb_model = joblib.load(XGB_MODEL_PATH)
            xgb_features = joblib.load(XGB_FEATURES_PATH)

            df_xgb = df.copy()
            for feat in xgb_features:
                if feat not in df_xgb.columns:
                    if "lag" in feat:
                        df_xgb[feat] = df_xgb["SSTA"] if "SSTA" in feat else df_xgb["current_speed"]
                    else:
                        df_xgb[feat] = 0.0

            df["chl"] = np.clip(xgb_model.predict(df_xgb[xgb_features].astype(np.float32)), 0.01, 15.0)
            print("🌱 Synthesized biological Chlorophyll-a layer via XGBoost regressor.")
            df["log_chl"] = np.log1p(df["chl"])
            df["chl_sst_ratio"] = df["chl"] / np.maximum(df["thetao"], 1.0)
            return df
        except Exception as e:
            print(f"⚠️ XGBoost biological synthesis bypassed: {e}")

    df["chl"] = 0.2
    df["log_chl"] = np.log1p(df["chl"])
    df["chl_sst_ratio"] = df["chl"] / np.maximum(df["thetao"], 1.0)
    return df

def detect_anomalies_and_regimes(df: pd.DataFrame) -> pd.DataFrame:
    """Run Isolation Forest anomaly scoring and classify oceanographic regimes."""
    iso_forest = joblib.load(ISO_FOREST_PATH)
    if isinstance(iso_forest, dict):
        iso_forest = iso_forest["pipeline"]
    model_features = joblib.load(ISO_FEATURES_PATH)

    for col in model_features:
        if col not in df.columns:
            if "chl" in col:
                df[col] = df["log_chl"] if "log_chl" in df.columns else 0.2
            elif "wind" in col:
                df[col] = 5.0
            else:
                df[col] = 0.0

    df["anomaly"] = iso_forest.predict(df[model_features])
    df["anomaly_score"] = iso_forest.decision_function(df[model_features])

    conditions = [
        (df["anomaly"] == -1) & (df["SSTA"] < -0.8) & (df["current_speed"] > 0.30),
        (df["anomaly"] == -1) & (df["SSTA"] > 1.2),
        (df["anomaly"] == -1)
    ]
    regimes = [
        "Productive Upwelling",
        "Thermal Stress (MHW)",
        "Dynamic Perturbation"
    ]
    df["marine_health_state"] = np.select(conditions, regimes, default="Stable Baseline")

    thermal_stability = np.clip(1.0 - (np.maximum(df["SSTA"], 0) / 2.5), 0, 1)
    circulation_flush = np.clip(df["current_speed"] / 0.5, 0, 1)
    df["MHI"] = (0.55 * thermal_stability + 0.45 * circulation_flush) * 100

    return df

def extract_spatial_events(df: pd.DataFrame, target_date: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster contiguous anomalous pixels using DBSCAN to generate footprint polygons."""
    date_str = target_date.strftime("%Y-%m-%d")
    event_records = []
    event_id_series = pd.Series("None", index=df.index, dtype="object")

    anom_mask = df["marine_health_state"] != "Stable Baseline"
    anom_slice = df[anom_mask]

    for state in anom_slice["marine_health_state"].unique():
        state_pts = anom_slice[anom_slice["marine_health_state"] == state]
        if len(state_pts) < 3:
            continue

        coords = state_pts[["latitude", "longitude"]].to_numpy()
        clustering = DBSCAN(eps=0.6, min_samples=3).fit(coords)

        for cluster_idx in set(clustering.labels_):
            if cluster_idx == -1:
                continue

            cluster_pts = state_pts[clustering.labels_ == cluster_idx]
            pixel_count = len(cluster_pts)
            clean_state = state.replace(" ", "_").replace("(", "").replace(")", "")
            uid = f"FC_{date_str.replace('-', '')}_{clean_state}_{cluster_idx}"

            event_id_series.loc[cluster_pts.index] = uid
            event_records.append({
                "event_id": uid,
                "time": date_str,
                "event_type": state,
                "pixel_count": pixel_count,
                "estimated_area_km2": pixel_count * 740,
                "centroid_lat": round(cluster_pts["latitude"].mean(), 2),
                "centroid_lon": round(cluster_pts["longitude"].mean(), 2),
                "min_SSTA": round(cluster_pts["SSTA"].min(), 2),
                "mean_MHI": round(cluster_pts["MHI"].mean(), 1)
            })

    df["event_id"] = event_id_series
    events_df = pd.DataFrame(event_records)
    return df, events_df

# ==============================================================================
# MAIN EXECUTION ROUTINE
# ==============================================================================
def run_forecast_pipeline(target_date: date | None = None) -> None:
    if target_date is None:
        target_date = date.today() + timedelta(days=1)

    date_str = target_date.strftime("%Y-%m-%d")
    print(f"\n🌊 ORCA Forecast Routine: {date_str}")
    print("=" * 60)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        print("📡 [1/4] Ingesting 24-hour CMEMS forecasts & satellite observations...")
        nc_files = download_cmems_forecast(target_date, temp_dir)

        print("🔄 [2/4] Processing physics & relative anomaly baselines...")
        df_forecast = ingest_and_engineer_physics(nc_files, target_date)

    df_forecast = estimate_biology_features(df_forecast)

    print("🧠 [3/4] Running Isolation Forest inference...")
    df_forecast = detect_anomalies_and_regimes(df_forecast)

    print("🗺️  [4/4] Extracting contiguous event footprints...")
    df_forecast, df_events = extract_spatial_events(df_forecast, target_date)

    df_forecast.to_parquet(PREDICTIONS_PARQUET_OUT, compression="snappy", index=False)
    df_events.to_csv(EVENTS_CSV_OUT, index=False)

    import shutil
    for sub in ["core_scripts", "orca_forecasting"]:
        dest_pq = PROJECT_ROOT / sub / "latest_forecast_predictions.parquet"
        dest_csv = PROJECT_ROOT / sub / "latest_forecast_events.csv"
        try:
            if dest_pq.resolve() != PREDICTIONS_PARQUET_OUT.resolve():
                shutil.copy2(PREDICTIONS_PARQUET_OUT, dest_pq)
            if dest_csv.resolve() != EVENTS_CSV_OUT.resolve():
                shutil.copy2(EVENTS_CSV_OUT, dest_csv)
        except Exception:
            pass

    print("\n✅ Forecast Routine Finished Successfully!")
    print(f"📍 Prediction Grid Cells Processed: {len(df_forecast):,}")
    print(f"📦 Files exported:\n   • {PREDICTIONS_PARQUET_OUT.name}\n   • {EVENTS_CSV_OUT.name}")
    print("\nRegime Distribution:")
    print(df_forecast["marine_health_state"].value_counts().to_string())

if __name__ == "__main__":
    run_forecast_pipeline()