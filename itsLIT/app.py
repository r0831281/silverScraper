import streamlit as st
import pandas as pd
import pydeck as pdk
from geopy.distance import geodesic
import math
import numpy as np

# Example: your locations
our_locations = {
    "Leuven": (50.8798, 4.7005),
    "Wezembeek-Oppem": (50.8392, 4.4945)
}

# Optimized haversine distance calculation (vectorized)
@st.cache_data
def haversine_vectorized(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees) using vectorized operations.
    Much faster than geopy for large datasets.
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    
    # Radius of earth in kilometers
    r = 6371
    return c * r

@st.cache_data
def load_and_process_data(file_content, file_name):
    """
    Load and process the uploaded file with caching for performance.
    """
    if file_name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_content)
    else:
        df = pd.read_csv(file_content, encoding='cp1252')
    
    # Standardize column names to lowercase immediately after loading
    df.columns = [col.lower() for col in df.columns]
    
    # Convert lat and lon to numeric, coercing errors to NaN
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    
    # Drop rows with missing lat or lon values
    df.dropna(subset=['lat', 'lon'], inplace=True)
    
    return df

# --- CORRECTED FUNCTION ---
# Function to generate points for a circle using geopy for accuracy
def generate_circle_points(latitude, longitude, radius_km, num_points=64):
    """
    Generates geodetically accurate points for a circle using the geopy library.
    """
    points = []
    center_point = (latitude, longitude)
    # Generate points for a full circle (0 to 360 degrees)
    for i in range(num_points + 1):
        bearing = i * (360 / num_points)
        # Use geopy to find the destination point
        destination = geodesic(kilometers=radius_km).destination(point=center_point, bearing=bearing)
        # Pydeck expects [longitude, latitude]
        points.append([destination.longitude, destination.latitude])
    return points


# Load data
uploaded_file = st.sidebar.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"], key="file_uploader")

if uploaded_file is not None:
    # Use cached loading function for performance
    with st.spinner("Loading and processing data..."):
        df = load_and_process_data(uploaded_file.getvalue(), uploaded_file.name)
    
    # Check for required columns to avoid key errors
    required_cols = ['lat', 'lon', 'city', 'profession']
    if not all(col in df.columns for col in required_cols):
        st.error(f"The uploaded file must contain the following columns: {required_cols}")
        st.stop()
    
    # Show dataset size information
    st.info(f"📊 Loaded {len(df):,} records from {uploaded_file.name}")

    # --- All the application logic that depends on 'df' goes here ---

    # Sidebar filters (use correct column names)
    st.sidebar.header("Filters")
    city_filter = st.sidebar.multiselect("Select city:", sorted(df["city"].unique()))
    specialty_filter = st.sidebar.multiselect("Select profession:", sorted(df["profession"].unique()))
    base_location = st.sidebar.selectbox("Choose base location:", list(our_locations.keys()))
    radius = st.sidebar.slider("Search radius (km):", 1, 150, 10)
    
    # Performance tips for large datasets
    if len(df) > 50000:
        st.sidebar.info(
            "💡 **Performance Tips:**\n"
            "- Use city filters to reduce data size\n"
            "- Smaller radius = faster calculations\n"
            "- Map shows max 5,000 points for performance"
        )

    # Optimize filtering operations
    # Apply filters efficiently before expensive distance calculations
    filtered = df
    
    # Apply city filter first (usually more selective)
    if city_filter:
        filtered = filtered[filtered["city"].isin(city_filter)]
    
    # Apply specialty filter
    if specialty_filter:
        filtered = filtered[filtered["profession"].isin(specialty_filter)]
    
    # Show filter impact
    if city_filter or specialty_filter:
        st.info(f"🔍 Filters reduced dataset from {len(df):,} to {len(filtered):,} records")

    # Apply distance filter using optimized calculation
    center_coords = our_locations[base_location]
    if not filtered.empty:
        with st.spinner(f"Calculating distances for {len(filtered):,} records..."):
            # Use vectorized haversine calculation (much faster than geopy)
            filtered = filtered.copy()
            filtered["Distance_km"] = haversine_vectorized(
                center_coords[0], center_coords[1],
                filtered["lat"].values, filtered["lon"].values
            )
            filtered = filtered[filtered["Distance_km"] <= radius]
    else:
        # If filtered is empty, add the Distance_km column as empty
        filtered["Distance_km"] = []

    # Aggregate data points by location to show count of overlapping points
    # Only calculate if needed for visualization
    aggregated_data = filtered.groupby(['lat', 'lon']).size().reset_index(name='count')
    
    # Memory optimization: clear unused variables for large datasets
    if len(df) > 100000:
        import gc
        gc.collect()

    # Main page title and KPIs
    st.title("Doctor Locator 📍")
    col1, col2 = st.columns(2)
    col1.metric("Doctors Found", len(filtered))
    col2.metric("Unique Professions", filtered["profession"].nunique())


    # Map visualization with performance optimization
    # For large datasets, sample data for map display to improve performance
    MAX_MAP_POINTS = 5000  # Limit map points for performance
    
    if len(filtered) >= MAX_MAP_POINTS:
        # Sample data for map display
        map_data = filtered.sample(n=MAX_MAP_POINTS, random_state=42)
        st.warning(f"⚡ Showing {MAX_MAP_POINTS:,} sampled points on map for performance (out of {len(filtered):,} total results)")
    else:
        map_data = filtered
        if len(filtered) == 0:
            st.info("No data available to display on the map.")
    # Prepare doctors data for tooltips (include name and riziv_nr)
    doctors_data = map_data[['lat', 'lon', 'name', 'riziv_nr', 'profession', 'city', 'Distance_km']].copy()
    # Map tooltip HTML for doctors
    tooltip_html = (
        "<b>Name:</b> {name}<br/>"
        "<b>RIZIV nr:</b> {riziv_nr}<br/>"
        "<b>Profession:</b> {profession}<br/>"
        "<b>City:</b> {city}<br/>"
        "<b>Distance (km):</b> {Distance_km}<br/>"
        "<b>Latitude:</b> {lat}<br/>"
        "<b>Longitude:</b> {lon}"
    )
    st.pydeck_chart(pdk.Deck(
        map_style="https://basemaps.cartocdn.com/gl/positron-nolabels-gl-style/style.json",
        initial_view_state=pdk.ViewState(
            latitude=center_coords[0],
            longitude=center_coords[1],
            zoom=10,
            pitch=0,
        ),
        tooltip={
            "html": tooltip_html,
            "style": {"color": "white"}
        },
        layers=[
            # Layer for the search radius using a PathLayer
            pdk.Layer(
                "PathLayer",
                data=pd.DataFrame([{'path': generate_circle_points(center_coords[0], center_coords[1], radius)}]),
                get_path='path',
                get_color=[255, 0, 0, 40],
                get_width=5,
                width_min_pixels=2,
            ),
            # Our base location marker
            pdk.Layer(
                "ScatterplotLayer",
                data=[{"lat": center_coords[0], "lon": center_coords[1], "count": 1}],
                get_position=["lon", "lat"],
                get_fill_color=[255, 0, 0, 200],
                get_radius=6,
                radius_units="pixels",
                pickable=True,
            ),
            # Doctors nearby with name and riziv_nr in tooltip
            pdk.Layer(
                "ScatterplotLayer",
                data=doctors_data,
                get_position=["lon", "lat"],
                get_fill_color=[0, 128, 255, 150],
                get_radius=8,
                pickable=True,
                radius_units="pixels",
                auto_highlight=True,
            ),
        ],
    ))
    
    # Display the filtered data with pagination for large datasets
    st.write("### Filtered Data")
    
    display_data = filtered[['name', 'riziv_nr', 'city', 'profession', 'Distance_km']].copy()
    
    # Sort by distance for better user experience
    if 'Distance_km' in display_data.columns:
        display_data = display_data.sort_values('Distance_km')
    
    # For large datasets, show top results and provide download option
    if len(display_data) > 1000:
        st.write(f"**Showing top 1000 closest results (out of {len(display_data):,} total)**")
        st.dataframe(display_data.head(1000), use_container_width=True)
        
        # Add download button for full results
        csv = display_data.to_csv(index=False)
        st.download_button(
            label=f"📥 Download all {len(display_data):,} results as CSV",
            data=csv,
            file_name=f"doctor_search_results_{len(display_data)}_records.csv",
            mime="text/csv"
        )
    else:
        st.dataframe(display_data, use_container_width=True)

else:
    st.info("Please upload a CSV or Excel file to begin.")
    st.stop()