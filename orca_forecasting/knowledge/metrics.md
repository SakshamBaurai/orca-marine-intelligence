# Oceanographic Metrics & Physical Parameters

## Sea Surface Temperature (SST / thetao)
- **Definition**: Sea Surface Temperature represents the thermodynamic temperature of the ocean's upper layer (skin to 5 meters depth), measured in degrees Celsius (°C).
- **Measurement**: Observed by satellite infrared/microwave radiometers (such as MODIS, VIIRS, and Sentinel-3 SLSTR) and predicted via numerical ocean circulation models (Copernicus Marine Environment Monitoring Service - CMEMS).
- **Ecological Role**: Temperature dictates metabolic rates of marine life, water density stratification, dissolved gas solubility, and thermal boundaries. In the Arabian Sea, typical surface temperatures range between 26.5°C and 30.5°C depending on season and monsoonal winds.
- **Fisheries Impact**: Pelagic fish species (such as Indian Mackerel, Sardines, and Yellowfin Tuna) exhibit narrow thermal comfort windows. Rapid thermal changes or sharp fronts often concentrate forage fish.

## Sea Surface Temperature Anomaly (SSTA)
- **Definition**: The deviation of current SST from the long-term historical climatological mean for that specific location and day of the year (°C).
- **Positive SSTA (+0.5°C to +2.5°C)**: Indicates warmer-than-normal surface waters. Prolonged strong positive anomalies indicate Marine Heatwaves (MHW), which cause thermal stress, coral bleaching, and drive pelagic fish deeper or offshore.
- **Negative SSTA (-0.2°C to -2.0°C)**: Indicates cooler-than-normal surface waters. In the coastal Arabian Sea, this is the primary signature of **active coastal upwelling**, where deep, cold, nutrient-rich water ascends to the sunlit surface layer.

## Salinity (so)
- **Definition**: The concentration of dissolved mineral salts in sea water, measured in Practical Salinity Units (PSU) or parts per thousand (g/kg).
- **Measurement**: Modeled by CMEMS physical assimilation and observed via satellite L-band radiometry (SMOS, SMAP) calibrated against in-situ Argo profiling floats.
- **Arabian Sea Context**: The Arabian Sea is characterized by exceptionally high surface salinity (typically 35.0 to 36.8 PSU) due to strong evaporation exceeding precipitation, particularly in the northern and western basins. Lower salinity pockets (33.5 to 35.0 PSU) occur along the southwest coast during the southwest monsoon due to coastal runoff.
- **Ecological Role**: Salinity gradients control water density and halocline stability, influencing the vertical distribution of plankton and pelagic eggs.

## Chlorophyll-a (chl)
- **Definition**: The primary photosynthetic green pigment found in marine phytoplankton, measured in milligrams per cubic meter (mg/m³).
- **Measurement**: Derived from ocean color radiometry via the Sentinel-3 Ocean and Land Colour Instrument (OLCI).
- **Ecological Role**: Chlorophyll-a serves as a direct proxy for phytoplankton biomass and primary productivity at the base of the marine food web.
- **Typical Values**:
  - Low (<0.2 mg/m³): Oligotrophic open ocean waters with low primary productivity.
  - Moderate (0.2 to 0.6 mg/m³): Typical productive coastal shelf waters.
  - High (0.6 to 3.5 mg/m³): Active upwelling zones and productive forage fronts. Favorable for schooling pelagic fish.
  - Very High (>4.0 mg/m³): Dense algal blooms; if coupled with water stagnation, may precede localized oxygen depletion.

## Sea Level Anomaly (SLA / sla)
- **Definition**: The height of the ocean surface above or below the mean sea surface, measured in meters (m) by satellite radar altimeters (Sentinel-3, Jason series).
- **Cyclonic Eddies (Negative SLA, -0.02m to -0.15m)**: Associated with divergent surface flow and **upwelling** of denser, colder subsurface water at the eddy core.
- **Anticyclonic Eddies (Positive SLA, +0.02m to +0.15m)**: Associated with convergent surface flow and **downwelling** of surface waters.

## Surface Ocean Currents (uo, vo, current_speed)
- **Definition**: Horizontal velocity of surface water, broken into eastward zonal velocity (uo) and northward meridional velocity (vo), with scalar speed in meters per second (m/s).
- **Role**: Currents transport heat, larvae, and nutrients. Shear zones where currents collide or diverge create natural physical aggregation boundaries for baitfish and predators.

## Sensor Constraints: Dissolved Oxygen & pH
- **Dissolved Oxygen (DO)**: Dissolved oxygen is vital for marine respiration. However, DO cannot be detected by satellite sensors because optical radiometers cannot penetrate beneath the surface skin. In-situ electrochemical sensors (CTD rosettes, Winkler titration, BGC-Argo floats) are strictly required.
- **Ocean Acidity / pH**: Ocean pH measures hydrogen ion activity on a logarithmic scale (typical ocean range: 8.05 to 8.25). Satellite sensors cannot measure pH directly; it requires spectrophotometric or potentiometric in-situ sensors.
- **ORCA Transparency Guarantee**: ORCA never invents or fakes DO or pH measurements when relying on satellite and surface forecast arrays. It transparently reports them as UNAVAILABLE with the scientific explanation.
