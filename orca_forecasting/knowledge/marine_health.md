# Marine Health Index & Anomaly Detection

## What is the Marine Health Index (MHI)?
- The **Marine Health Index (MHI)** is a normalized composite score ranging from **0 to 100** that evaluates the ecological stability and biophysical normalcy of the ocean environment.
- **Score Scale**:
  - **75 to 100 (Optimal / Healthy - Green)**: Balanced thermal regime, normal salinity, healthy phytoplankton forage levels, and stable circulation. Minimal ecosystem stress.
  - **55 to 74 (Moderate / Monitored - Yellow / Amber)**: Mild environmental deviations, such as slight warming, elevated wind shear, or localized transitional fronts. Normal for seasonal shift periods.
  - **0 to 54 (Stressed / Anomaly Alert - Red / Coral)**: Acute ecological disturbance. Typical drivers include intense Marine Heatwaves (elevated SSTA > +1.5°C), severe hypoxia risk, abnormal stratification, or extreme freshwater lens events.

## Why is an Area Green or Red on the Map?
- **Green Areas**: Indicate waters where all physical parameters (SST, salinity, currents, chlorophyll) fall within historical climatological bounds. The habitat is stable, supporting thriving pelagic ecosystems and normal food-web dynamics.
- **Red Areas**: Indicate waters flagged as an anomalous disturbance. This does not always mean pollution; rather, it indicates severe physical anomalies like a **Marine Heatwave** (water significantly hotter than usual), an intense thermal disturbance, or sudden physical divergence. Fish may avoid or dive below these warm surface layers.

## The ORCA Isolation Forest Detector
- **Model Architecture**: An unsupervised ensemble of decision trees trained on multi-decadal Copernicus ocean reanalysis.
- **Feature Matrix**: Standardized local z-score anomalies of temperature, salinity, currents, chlorophyll, and sea level anomaly.
- **No Data Leakage**: Evaluated against historical baselines without contamination across temporal folds.
- **Ecological State Classification**:
  - `Stable baseline`: Normal conditions within 1 standard deviation of climatology.
  - `Dynamic perturbation`: Transitional front or mesoscale eddy causing mild shifts.
  - `Thermal stress / MHW`: Prolonged abnormally warm surface water threatening marine life.
