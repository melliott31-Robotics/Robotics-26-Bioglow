
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Public Wildlife Database",
    page_icon="🦉",
    layout="wide",
)

st.title("🦉 St. Louis Project Wildlife Database")
st.write(
    "Explore wildlife observations submitted by community members. "
    "Only general locations should be shared publicly."
)

# Locate the project's data file.
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_DIR / "wildlife_data" / "submissions.csv"

if not DATA_FILE.exists():
    st.info(
        "No observations have been submitted yet. "
        "New observations will appear here once they are saved."
    )
    st.caption(
        "This database is waiting for its first research submission."
    )
    st.stop()

try:
    df = pd.read_csv(DATA_FILE)
except (OSError, pd.errors.ParserError):
    st.error("The observations file could not be read.")
    st.stop()

if df.empty:
    st.info("There are no observations to display yet.")
    st.stop()

# Match column names without assuming a particular capitalization.
columns = {str(col).strip().lower(): col for col in df.columns}

def find_column(*possible_names):
    for name in possible_names:
        if name.lower() in columns:
            return columns[name.lower()]
    return None

species_col = find_column("species", "species_name", "common_name")
date_col = find_column("date", "observation_date", "observed_date")
habitat_col = find_column("habitat", "habitat_type")
location_col = find_column(
    "general_location", "location", "area", "region"
)

# Do not display columns that could contain personal or precise location data.
private_words = (
    "email", "phone", "full_name", "first_name", "last_name",
    "address", "latitude", "longitude", "coordinates", "gps",
    "exact_location", "precise_location", "submission_pin",
)


# Only these approved research fields may be displayed publicly.
PUBLIC_COLUMNS = [
    "bird_name",
    "approximate_count",
    "location",
    "observation_date",
    "observation_time",
]

# Include only approved fields that exist in the CSV.
available_columns = [
    column for column in PUBLIC_COLUMNS
    if column in df.columns
]

public_df = df[available_columns].copy()

# Give the public page readable column names.
public_df = public_df.rename(columns={
    "bird_name": "Species",
    "approximate_count": "Approximate Count",
    "location": "General Location",
    "observation_date": "Observation Date",
    "observation_time": "Observation Time",
    "submission_mode": "Identification Method",
})

st.subheader("Filter observations")

f1, f2 = st.columns(2)

with f1:
    if "Species" in public_df.columns:
        temp_species_values = sorted(
            public_df["Species"].dropna().astype(str).str.split(r';\s*').explode().unique()
        )
        raw_species_values = pd.Series([temp_species_values]).iloc[0]

        species_values = list(dict.fromkeys(raw_species_values))
        
        selected_species = st.multiselect("Species", species_values)
    else:
        selected_species = []

with f2:
    if "General Location" in public_df.columns:
        location_values = sorted(
            public_df["General Location"].dropna().astype(str).unique()
        )
        selected_locations = st.multiselect(
            "General location", location_values
        )
    else:
        selected_locations = []

filtered = public_df.copy()

if selected_species:
    filtered = filtered[
        filtered["Species"].astype(str).apply(lambda cell: any(item.strip() in selected_species for item in cell.split(";")))
    ]

if selected_locations:
    filtered = filtered[
        filtered["General Location"].astype(str).isin(selected_locations)
    ]

if "Observation Date" in filtered.columns:
    parsed_dates = pd.to_datetime(
        filtered["Observation Date"], errors="coerce"
    )
    valid_dates = parsed_dates.dropna()

    if not valid_dates.empty:
        min_date = valid_dates.min().date()
        max_date = valid_dates.max().date()

        date_range = st.date_input(
            "Observation date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            keep_rows = (
                parsed_dates.dt.date.between(start_date, end_date)
                | parsed_dates.isna()
            )
            filtered = filtered[keep_rows]


st.subheader(f"{len(filtered)} observation(s)")

# Browse all observations in a table.
st.dataframe(
    filtered,
    use_container_width=True,
    hide_index=True,
)

# Select an observation to see its details.
if not filtered.empty:
    st.subheader("Explore an observation")

    def observation_label(row_id):
        row = filtered.loc[row_id]
        species = row.get("Species", "Unknown species")
        date = row.get("Observation Date", "Date unknown")
        location = row.get("General Location", "Location unknown")
        return f"{species} | {date} | {location}"

    selected_id = st.selectbox(
        "Choose an observation",
        options=filtered.index.tolist(),
        format_func=observation_label,
    )

    selected = filtered.loc[selected_id]

    st.subheader(str(selected.get("Species", "Wildlife observation")))

    left, right = st.columns(2)

    with left:
        st.write("**Date:**", selected.get("Observation Date", "Not recorded"))
        st.write("**Time:**", selected.get("Observation Time", "Not recorded"))
        st.write("**General location:**", selected.get("General Location", "Not recorded"))
        st.write("**Habitat:**", selected.get("Habitat", "Not recorded"))

    with right:
        st.write("**Approximate count:**", selected.get("Approximate Count", "Not recorded"))
        st.write("**Behavior:**", selected.get("Behavior", "Not recorded"))
        st.write("**Identification method:**", selected.get("Identification Method", "Not recorded"))

    # Display saved photos and audio for this observation.
    media_dir = PROJECT_DIR / "wildlife_data"

    image_files = str(
        df.loc[selected_id].get("image_files", "") or ""
    )
    audio_files = str(
        df.loc[selected_id].get("audio_files", "") or ""
    )

    st.subheader("Photos")
    if image_files.strip():
        for filename in image_files.split(";"):
            filename = filename.strip()
            if not filename:
                continue

            # Only allow files inside the project's images folder.
            image_path = (
                media_dir / "images" / Path(filename).name
            ).resolve()
            safe_image_dir = (media_dir / "images").resolve()

            if image_path.is_relative_to(safe_image_dir) and image_path.is_file():
                st.image(str(image_path), caption="Observation photo")
    else:
        st.write("No photos attached.")

    st.subheader("Audio recordings")
    if audio_files.strip():
        for filename in audio_files.split(";"):
            filename = filename.strip()
            if not filename:
                continue

            audio_path = (
                media_dir / "audio" / Path(filename).name
            ).resolve()
            safe_audio_dir = (media_dir / "audio").resolve()

            if audio_path.is_relative_to(safe_audio_dir) and audio_path.is_file():
                with open(audio_path, "rb") as audio_file:
                    st.audio(audio_file.read())
    else:
        st.write("No audio recordings attached.")

else:
    st.info("No observations match the selected filters.")


