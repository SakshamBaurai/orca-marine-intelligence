import streamlit as st
import pandas as pd
from branca.element import Template, MacroElement
import folium
from streamlit_folium import st_folium
import datetime
import os
from pathlib import Path

# -------------------------------------------------------------
# 1. Page Configuration & Styling
# -------------------------------------------------------------
st.set_page_config(
    page_title="ORCA - Arabian Sea Ocean Intelligence",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        .block-container {padding-top: 1.2rem; padding-bottom: 1.5rem;}
        [data-testid="stMetricValue"] {font-size: 1.7rem;}
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 2. Resilient Pathing & Cached Data Loaders
# -------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent if BASE_DIR.name == "core_scripts" else BASE_DIR

HIST_DATA_PATH = (
    PROJECT_ROOT / "orca_processed_ocean_data.parquet" if (PROJECT_ROOT / "orca_processed_ocean_data.parquet").exists()
    else BASE_DIR / "orca_processed_ocean_data.parquet"
)
HIST_EVENTS_PATH = (
    PROJECT_ROOT / "orca_detected_events_2022_2025.csv" if (PROJECT_ROOT / "orca_detected_events_2022_2025.csv").exists()
    else BASE_DIR / "orca_detected_events_2022_2025.csv"
)
FC_DATA_PATH = (
    PROJECT_ROOT / "latest_forecast_predictions.parquet" if (PROJECT_ROOT / "latest_forecast_predictions.parquet").exists()
    else BASE_DIR / "latest_forecast_predictions.parquet"
)
FC_EVENTS_PATH = (
    PROJECT_ROOT / "latest_forecast_events.csv" if (PROJECT_ROOT / "latest_forecast_events.csv").exists()
    else BASE_DIR / "latest_forecast_events.csv"
)

@st.cache_data
def load_historical_data():
    if HIST_DATA_PATH.exists() and HIST_EVENTS_PATH.exists():
        df = pd.read_parquet(HIST_DATA_PATH)
        df['time'] = pd.to_datetime(df['time']).dt.date
        events = pd.read_csv(HIST_EVENTS_PATH)
        events['time'] = pd.to_datetime(events['time']).dt.date
        return df, events
    return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=3600)
def load_forecast_data():
    if FC_DATA_PATH.exists() and FC_EVENTS_PATH.exists():
        df_fc = pd.read_parquet(FC_DATA_PATH)
        df_fc['time'] = pd.to_datetime(df_fc['time']).dt.date
        events_fc = pd.read_csv(FC_EVENTS_PATH)
        events_fc['time'] = pd.to_datetime(events_fc['time']).dt.date
        return df_fc, events_fc
    return None, None

df_hist, events_hist = load_historical_data()
df_fc, events_fc = load_forecast_data()

# -------------------------------------------------------------
# 3. Sidebar Mode Selection & Controls
# -------------------------------------------------------------
st.sidebar.title("🌊 ORCA Controller")
st.sidebar.caption("Real-Time Marine Health & Upwelling Engine")
st.sidebar.divider()

view_mode = st.sidebar.radio(
    "Operational Mode:",
    ["Historical Archives (2022–2025)", "24-Hour AI Predictive Forecast"]
)

if view_mode == "Historical Archives (2022–2025)":
    if df_hist.empty:
        st.sidebar.error("Historical data not found. Check file paths.")
        st.stop()
        
    min_d, max_d = df_hist['time'].min(), df_hist['time'].max()
    default_d = datetime.date(2022, 8, 4) if min_d <= datetime.date(2022, 8, 4) <= max_d else min_d
    selected_date = st.sidebar.date_input("Select Date:", value=default_d, min_value=min_d, max_value=max_d)
    
    day_data = df_hist[df_hist['time'] == selected_date]
    day_events = events_hist[events_hist['time'] == selected_date]
    mode_tag = "Historical Observation"

else:
    if df_fc is not None and not df_fc.empty:
        selected_date = df_fc['time'].iloc[0]
        day_data = df_fc[df_fc['time'] == selected_date]
        day_events = events_fc[events_fc['time'] == selected_date]
        mode_tag = "⚡ 24-Hour Ahead AI Predictive Forecast"
        st.sidebar.success(f"Loaded Forecast: {selected_date}")
    else:
        st.sidebar.error("Forecast data missing. Run `python predict_forecast.py` first.")
        st.stop()

st.sidebar.divider()
st.sidebar.subheader("Layer Diagnostics")
show_upwelling = st.sidebar.checkbox("Productive Upwelling (PFZ)", value=True)
show_mhw = st.sidebar.checkbox("Thermal Stress (Marine Heatwaves)", value=True)
show_eutro = st.sidebar.checkbox("Eutrophication / Hypoxia Risk", value=True)
show_jets = st.sidebar.checkbox("Dynamic Perturbations (Fronts/Jets)", value=True)
show_baseline = st.sidebar.checkbox("Baseline Ocean (Sampled)", value=False)

 
st.title(f"{mode_tag} — {selected_date.strftime('%B %d, %Y')}")

upwelling_slice = day_data[day_data['marine_health_state'] == 'Productive Upwelling']
total_area = day_events[day_events['event_type'] == 'Productive Upwelling']['estimated_area_km2'].sum() if not day_events.empty else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Predicted Upwelling Footprint", f"{total_area:,} km²")
c2.metric("Cold Core (Min SSTA)", f"{day_data['SSTA'].min():.2f} °C" if len(day_data) else "0.00 °C")
c3.metric("Peak Marine Health Index", f"{day_data['MHI'].max():.1f} / 100" if len(day_data) else "N/A")
c4.metric("Active Anomaly Grid Cells", f"{len(day_data[day_data['marine_health_state'] != 'Stable Baseline']):,}")

st.divider()

# -------------------------------------------------------------
# 5. Geospatial Map & Tactical Advisory
# -------------------------------------------------------------
col_map, col_info = st.columns([2.2, 1])

with col_map:
    
    st.subheader("Geospatial Diagnostic Map")
    
    # Satellite Imagery Base Layer
    m = folium.Map(
        location=[14.5, 71.5],
        zoom_start=6,
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri Satellite'
    )
    
    
    color_map = {
        'Productive Upwelling': ('#00ff7f', show_upwelling),
        'Thermal Stress (MHW)': ('#ff3333', show_mhw),
        'Eutrophication Risk': ('#bf00ff', show_eutro),
        'Dynamic Perturbation': ('#3399ff', show_jets)
    }

    # Baseline ocean background
    if show_baseline and 'Stable Baseline' in day_data['marine_health_state'].values:
        for _, row in day_data[day_data['marine_health_state'] == 'Stable Baseline'].iloc[::4].iterrows():
            folium.CircleMarker(
                location=[row['latitude'], row['longitude']],
                radius=1.5,
                color='#888888',
                fill=True,
                fill_opacity=0.3
            ).add_to(m)

    # Diagnostic anomaly layers
    for state, (color, is_visible) in color_map.items():
        if is_visible:
            subset = day_data[day_data['marine_health_state'] == state]
            for _, row in subset.iloc[::2].iterrows():
                popup_html = f"""
                <div style="font-family: sans-serif; font-size: 11px;">
                    <b>State:</b> <span style="color:{color};">{state}</span><br>
                    <b>SSTA:</b> {row['SSTA']:.2f} °C<br>
                    <b>Current Speed:</b> {row.get('current_speed', 0.0):.2f} m/s<br>
                    <b>MHI Score:</b> {row['MHI']:.1f}/100
                </div>
                """
                folium.CircleMarker(
                    location=[row['latitude'], row['longitude']],
                    radius=3.5,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.85,
                    popup=folium.Popup(popup_html, max_width=220)
                ).add_to(m)

    # Event centroids
    if not day_events.empty:
        for _, evt in day_events.iterrows():
            folium.Marker(
                location=[evt['centroid_lat'], evt['centroid_lon']],
                popup=f"Event: {evt['event_id']}<br>Area: {evt['estimated_area_km2']:,} km²",
                icon=folium.Icon(color='green' if 'Upwelling' in evt['event_type'] else 'red', icon='info-sign')
            ).add_to(m)

    # ---------------------------------------------------------
    # HTML Map Key (Legend) Overlay
    # ---------------------------------------------------------
    legend_html = '''
    {% macro html(this, kwargs) %}
    <div style="
        position: fixed; 
        bottom: 30px;
        left: 30px;
        width: 190px;
        height: auto;
        z-index: 9999;
        font-family: sans-serif;
        font-size: 12px;
        background-color: rgba(255, 255, 255, 0.9);
        border: 1px solid grey;
        border-radius: 5px;
        padding: 10px;
        box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
        ">
        <b style="color: black; margin-bottom: 5px; display: block;">Map Key</b>
        <div style="margin-bottom: 3px;"><i style="background:#00ff7f; width:12px; height:12px; float:left; margin-right:8px; border-radius:50%;"></i> <span style="color: black;">Upwelling (PFZ)</span></div>
        <div style="margin-bottom: 3px;"><i style="background:#ff3333; width:12px; height:12px; float:left; margin-right:8px; border-radius:50%;"></i> <span style="color: black;">Thermal Stress</span></div>
        <div style="margin-bottom: 3px;"><i style="background:#bf00ff; width:12px; height:12px; float:left; margin-right:8px; border-radius:50%;"></i> <span style="color: black;">Eutrophication</span></div>
        <div style="margin-bottom: 3px;"><i style="background:#3399ff; width:12px; height:12px; float:left; margin-right:8px; border-radius:50%;"></i> <span style="color: black;">Perturbation</span></div>
        <div style="margin-bottom: 3px;"><i style="background:#888888; width:12px; height:12px; float:left; margin-right:8px; border-radius:50%; opacity:0.6;"></i> <span style="color: black;">Baseline Ocean</span></div>
    </div>
    {% endmacro %}
    '''
    
    macro = MacroElement()
    macro._template = Template(legend_html)
    m.get_root().add_child(macro)
    
    # Render without returning viewport state to eliminate rerun loops
    st_folium(m, width="100%", height=560, returned_objects=[])
 
with col_info:
    st.subheader("Clustered Events")
    if not day_events.empty:
        st.dataframe(
            day_events[['event_type', 'estimated_area_km2', 'centroid_lat', 'centroid_lon']],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No multi-pixel clustered events detected.")

    st.subheader("🎣 Commercial Fishing Advisory")
    if not upwelling_slice.empty:
        st.success(f"**{len(upwelling_slice)} Target Coordinates Flagged**")
        pfz_export = upwelling_slice[['latitude', 'longitude', 'SSTA', 'current_speed', 'MHI']].copy()
        pfz_export.columns = ['Lat', 'Lon', 'SSTA (°C)', 'Current (m/s)', 'MHI Score']
        
        st.download_button(
            label="📥 Download Target Coordinates (CSV)",
            data=pfz_export.to_csv(index=False).encode('utf-8'),
            file_name=f"ORCA_Target_Advisory_{selected_date}.csv",
            mime="text/csv",
            use_container_width=True
        )
    else:
        st.warning("No high-vitality upwelling zones flagged for this timeframe.")