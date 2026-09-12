# ORCA Forecasting Methodology & Data Provenance

## Data Sources & Provenance
ORCA operates strictly on verifiable, authentic datasets with complete scientific integrity:
1. **Copernicus Marine Service (CMEMS)**:
   - Physical Global Analysis and Forecast: Daily sea surface temperature (`thetao`), sea water salinity (`so`), horizontal currents (`uo`, `vo`), and sea surface height (`sla`).
   - Spatial Grid: Gridded ocean observation cells across the Eastern Arabian Sea (65.0°E to 77.5°E, 8.0°N to 24.5°N).
2. **Copernicus Ocean Color (Sentinel-3 OLCI)**:
   - Near-real-time optical radiometry measuring surface Chlorophyll-a (`chl`) in mg/m³.
3. **Open-Meteo Coastal Meteorological API**:
   - Live real-time coastal weather telemetry: air temperature (2m), wind speed (10m), and relative humidity for coastal harbours and ports.
4. **Historical Baseline & Climatology**:
   - Standardized multi-decadal monthly climatology baselines. Z-scores are computed independently per geographic cell and season to eliminate artificial drift and data leakage.

## The 24-48 Hour Forecast Cycle
- Forecast predictions (`latest_forecast_predictions.parquet`) are computed on 24-hour assimilation windows.
- When users ask about tomorrow or forecast trends, ORCA analyzes the multi-parameter vector:
  - If SSTA trend is cooling accompanied by chlorophyll increase: Upwelling intensification $\rightarrow$ Favorable fishing outlook.
  - If SSTA trend is warming (+1.5°C) with declining currents: Stratification and thermal stress $\rightarrow$ Declining suitability.
  - If wind speeds exceed 35 km/h via Open-Meteo: Adverse surface sea state regardless of water temperature.
