import streamlit as st
import pandas as pd
import pydeck as pdk
from geopy.distance import geodesic
import math

# Example: your locations
our_locations = {
    "Leuven": (50.8798, 4.7005),
    "Wezembeek-Oppem": (50.8392, 4.4945)
}

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
    if uploaded_file.name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        # Use a more robust encoding for CSV files that might not be UTF-8
        df = pd.read_csv(uploaded_file, encoding='cp1252')
    
    # Standardize column names to lowercase immediately after loading
    df.columns = [col.lower() for col in df.columns]

    # Check for required columns to avoid key errors
    required_cols = ['lat', 'lon', 'city', 'profession']
    if not all(col in df.columns for col in required_cols):
        st.error(f"The uploaded file must contain the following columns: {required_cols}")
        st.stop()

    # Convert lat and lon to numeric, coercing errors to NaN
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
    
    # Drop rows with missing lat or lon values to ensure map rendering works correctly
    df.dropna(subset=['lat', 'lon'], inplace=True)

    # --- All the application logic that depends on 'df' goes here ---

    # Sidebar filters (use correct column names)
    st.sidebar.header("Filters")
    city_filter = st.sidebar.multiselect("Select city:", sorted(df["city"].unique()))
    specialty_filter = st.sidebar.multiselect("Select profession:", sorted(df["profession"].unique()))
    base_location = st.sidebar.selectbox("Choose base location:", list(our_locations.keys()))
    radius = st.sidebar.slider("Search radius (km):", 1, 150, 10)

    # Filter data
    filtered = df.copy()
    if city_filter:
        filtered = filtered[filtered["city"].isin(city_filter)]
    if specialty_filter:
        filtered = filtered[filtered["profession"].isin(specialty_filter)]

    # Apply distance filter
    center_coords = our_locations[base_location]
    filtered["Distance_km"] = filtered.apply(
        lambda row: geodesic(center_coords, (row["lat"], row["lon"])).km, axis=1
    )
    filtered = filtered[filtered["Distance_km"] <= radius]

    # Aggregate data points by location to show count of overlapping points
    aggregated_data = filtered.groupby(['lat', 'lon']).size().reset_index(name='count')

    # Main page title and KPIs
    st.title("Doctor Locator 📍")
    col1, col2 = st.columns(2)
    col1.metric("Doctors Found", len(filtered))
    col2.metric("Unique Professions", filtered["profession"].nunique())


    # Map visualization
    # Prepare doctors data for tooltips (include name and riziv_nr)
    doctors_data = filtered[['lat', 'lon', 'name', 'riziv_nr', 'profession', 'city', 'Distance_km']].copy()
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
    
    # Display the filtered data in a table, including name and riziv_nr
    st.write("### Filtered Data")
    st.dataframe(
        filtered[['name', 'riziv_nr', 'city', 'profession', 'Distance_km']]
        .sort_values('Distance_km')
        .round({'Distance_km': 2})
    )

else:
    st.info("Please upload a CSV or Excel file to begin.")
    st.stop()