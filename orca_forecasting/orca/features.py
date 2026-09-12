import numpy as np
import pandas as pd
from .climatology import Climatology
from .config import DataConfig

def build_features(df: pd.DataFrame, climatology: Climatology, data_cfg: DataConfig | None = None, check_finite: bool = True) -> pd.DataFrame:
    feats = pd.DataFrame(index=df.index)
    
    df_copy = df.copy()
    if "time" in df_copy.columns:
        df_copy["time_day"] = pd.to_datetime(df_copy["time"]).dt.date
    else:
        df_copy["time_day"] = "2026-09-11"
        
    feats["thetao_daily_anomaly"] = df_copy["thetao"] - df_copy.groupby("time_day")["thetao"].transform("mean")
    feats["so_daily_anomaly"] = df_copy["so"] - df_copy.groupby("time_day")["so"].transform("mean")
    feats["sla_daily_anomaly"] = df_copy["sla"] - df_copy.groupby("time_day")["sla"].transform("mean")
    
    feats["uo"] = df["uo"].astype("float32")
    feats["vo"] = df["vo"].astype("float32")
    feats["current_speed"] = np.hypot(df["uo"], df["vo"]).astype("float32")
    feats["u10"] = df["u10"].astype("float32")
    feats["v10"] = df["v10"].astype("float32")
    feats["wind_speed"] = np.hypot(df["u10"], df["v10"]).astype("float32")
    feats["log_chl"] = np.log1p(df["chl"]).astype("float32")

    order = [
        "thetao_daily_anomaly", "so_daily_anomaly", "sla_daily_anomaly",
        "uo", "vo", "current_speed", "u10", "v10", "wind_speed", "log_chl"
    ]
    feats = feats[order].astype("float32")
    feats = feats.fillna(0)
    return feats
