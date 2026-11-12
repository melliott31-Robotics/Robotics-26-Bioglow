import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# --------------------------------------------------
# Page setup and storage
# --------------------------------------------------

st.set_page_config(
    page_title="Bird Observation Form",
    page_icon="🐦",
    layout="wide",
)

# Assumes this file is inside your project's pages folder.
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "wildlife_data"
IMAGE_DIR = DATA_DIR / "images"
AUDIO_DIR = DATA_DIR / "audio"
CSV_FILE = DATA_DIR / "submissions.csv"
CSV_FILE2 = DATA_DIR / "submissions2.csv"

for folder in (DATA_DIR, IMAGE_DIR, AUDIO_DIR):
    folder.mkdir(parents=True, exist_ok=True)

st.title("🐦 St. Louis Project Wildlife Database")
st.write(
    "Record a bird observation, upload media, and optionally "
    "identify bird species from audio using BirdNET."
)

# --------------------------------------------------
# BirdNET model: loaded once and reused
# --------------------------------------------------

@st.cache_resource(show_spinner=False)
def load_birdnet_model():
    import birdnet
    acoustic_model = birdnet.load("acoustic", "3.0", "onnx")
    geo_model = geo_model = birdnet.load("geo", "3.0", "pb")
    return acoustic_model, geo_model


# --------------------------------------------------
# Helper functions
# --------------------------------------------------

def save_uploads(uploaded_files, destination_folder, submission_id):
    saved_paths = []

    for uploaded_file in uploaded_files or []:
        suffix = Path(uploaded_file.name).suffix.lower()

        # Create a unique filename to avoid overwriting files.
        filename = f"{submission_id}_{uuid.uuid4().hex}{suffix}"
        destination = destination_folder / filename
        destination.write_bytes(uploaded_file.getvalue())

        saved_paths.append(str(destination.relative_to(PROJECT_DIR)))

    return saved_paths



def identify_bird_audio(acoustic_model, geo_model, audio_path):
    """Identify bird species and filter out non-local species using BirdNET's geo model."""
    import pandas as pd
    from datetime import date

    predictions = acoustic_model.predict(str(audio_path))

    if isinstance(predictions, pd.DataFrame):
        df = predictions
    elif hasattr(predictions, "to_dataframe"):
        df = predictions.to_dataframe()
    elif hasattr(predictions, "to_pandas"):
        df = predictions.to_pandas()
    else:
        df = pd.DataFrame(predictions)

    if df.empty or not {"species_name", "confidence"}.issubset(df.columns):
        return []

    today = date.today()
    birdnet_week = min(48, max(1, (today.month - 1) * 4 + (today.day - 1) // 7 + 1))

    geo_predictions = geo_model.predict(
        38.5665,
        -90.3938,
        week=birdnet_week
    )
    geo_df = geo_predictions.to_dataframe() if hasattr(geo_predictions, "to_dataframe") else pd.DataFrame(geo_predictions)

    # Keep species with at least a 3% chance of being in your area right now
    local_species = set(geo_df[geo_df["confidence"] >= 0.03]["species_name"])

    df = df[df["species_name"].isin(local_species)]

    if df.empty:
        return []

    results = (
        df.dropna(subset=["species_name", "confidence"])
        .groupby("species_name", as_index=False)["confidence"]
        .max()
        .sort_values("confidence", ascending=False)
    )

    results = results[results["confidence"] >= 0.70].head(5)

    output = []
    for _, row in results.iterrows():
        raw_name = str(row["species_name"])
        parts = raw_name.split("_", 1)

        output.append({
            "species": parts[1] if len(parts) == 2 else "",
            "scientific_name": parts[0] if len(parts) == 2 else raw_name,
            "score": round(float(row["confidence"]), 4),
        })

    return output


def append_record(record):
    new_record = pd.DataFrame([record])
    needs_header = (
        not CSV_FILE.exists() or CSV_FILE.stat().st_size == 0
    )

    new_record.to_csv(
        CSV_FILE,
        mode="a",
        header=needs_header,
        index=False,
        encoding="utf-8",
    )
def append_record2(record):
    # 1. Define the file path for your matrix CSV layout
    # (Matches your wildlife folder setup)
    MATRIX_FILE = DATA_DIR / "submissions2.csv"
    
    # 2. Extract and format the incoming data values
    # Extract only the very first bird before the semicolon
    import json
    birds = []
    raw_results = record.get("birdnet_results", [])
    if isinstance(raw_results, str):
        raw_results = json.loads(raw_results) if raw_results.strip() else []
    for item in raw_results:
        for pred in item.get("predictions", []):
            name = str(pred.get("species", "")).strip()
            if name and name not in birds:
                birds.append(name)

    if not birds:
        raw_bird_string = str(record.get("bird_name", "Unknown"))
        birds = [b.strip() for b in raw_bird_string.split(";") if b.strip()] or ["Unknown"]
    
    # Grab the date of observation
    current_day = str(record.get("observation_date"))
    
    # 3. Load or initialize the matrix DataFrame
    if MATRIX_FILE.exists() and MATRIX_FILE.stat().st_size > 0:
        grid_df = pd.read_csv(MATRIX_FILE, index_col=0)
    else:
        # If the file is completely new, start a blank grid with the Species index column
        grid_df = pd.DataFrame(columns=["Species"]).set_index("Species")
        
    # 4. Handle any missing historical days automatically
    # This checks for gaps between existing columns and the incoming date
    if grid_df.columns.size > 0:
        try:
            # Parse existing columns as dates to find the earliest recorded day
            existing_dates = pd.to_datetime(grid_df.columns)
            min_date = existing_dates.min().date()
            target_date = pd.to_datetime(current_day).date()
            
            if target_date > min_date:
                # Generate a complete daily calendar range up to the new date
                full_range = pd.date_range(start=min_date, end=target_date).strftime('%Y-%m-%d')
                # Reindex columns to fill missing dates with 0
                grid_df = grid_df.reindex(columns=full_range, fill_value=0)
        except Exception:
            pass # Fallback to standard column insertion if parsing styles mismatch

    # 5. Insert the new Day column if it still doesn't exist
    if current_day not in grid_df.columns:
        grid_df[current_day] = 0

    # 6 & 7. Insert a row for EVERY bird and set today's sighting to 1
    for bird in birds:
        if bird not in grid_df.index:
            grid_df.loc[bird] = 0
        grid_df.at[bird, current_day] = 1

    # 8. Clean up formatting: Sort species alphabetically, dates chronologically
    grid_df = grid_df.sort_index()  # Sort rows
    try:
        sorted_date_cols = sorted(grid_df.columns, key=pd.to_datetime)
        grid_df = grid_df[sorted_date_cols]  # Sort columns
    except Exception:
        grid_df = grid_df.reindex(sorted(grid_df.columns), axis=1)

    # 9. Overwrite the file with the updated matrix grid
    grid_df.to_csv(MATRIX_FILE, index=True, encoding="utf-8")


# --------------------------------------------------
# Choose a submission mode
# --------------------------------------------------

mode = st.radio(
    "How would you like to submit your observation?",
    ["Audio identification", "Manual observation"],
    horizontal=True,
)

if mode == "Audio identification":
    st.info(
        "Upload a recording and BirdNET will suggest possible species. "
        "You do not need to know the bird's name."
    )
else:
    st.info(
        "Enter the bird's name if you know it. Audio and photos are optional."
    )

# --------------------------------------------------
# Observation form
# --------------------------------------------------

with st.form("bird_observation_form", clear_on_submit=False):

    st.subheader("1. Observation details")

    if mode == "Manual observation":
        bird_name = st.text_input(
            "Bird name (optional)",
            placeholder="e.g. Northern Cardinal, or leave blank",
        )
    else:
        bird_name = ""

    count_options = [
        "1", "2–5", "6–10", "11–25", "26–50",
        "51–100", "100+", "500+", "1,000+", "10,000+", "Unknown",
    ]
    approximate_count = st.selectbox(
        "Approximate number of birds *",
        count_options,
    )
    cam_selection = ["Cam1",
            "Cam2",
            "Cam3",
            "Cam4",
            "Cam5",
            "Cam6",
            "Cam7",
            "Cam8",
            "Cam9",
            "Cam10",
            "Cam11",
            "Cam12",
            "Cam13",
            "Cam14",
            "Cam15",
            "Cam16",
            "Cam17",
            "Cam18",
            "Cam19",
            "Cam20",
            "Cam21",
            "Cam22",
            "Cam23",
            "Cam24",
            "Cam25",
            "Cam26",
            "Cam27",
            "Cam28",
            "Cam29",
            "Cam30",
            "Cam31",
            "Cam32",
            "Cam33",
            "Cam34"]
    location = st.selectbox(
        "Camera Number*",
        cam_selection
    )

    col1, col2 = st.columns(2)

    with col1:
        observation_date = st.date_input(
            "Date observed *",
            value=date.today(),
            max_value=date.today(),
        )

    with col2:
        observation_time = st.time_input(
            "Time observed *",
            value=datetime.now().time().replace(second=0, microsecond=0),
        )



    st.subheader("2. Upload media")

    # BirdNET's Python library supports WAV, MP3, FLAC and OGG.
    # M4A is not supported by the documented audio-reading workflow.
    if mode == "Audio identification":
        audio_files = st.file_uploader(
            "Upload bird audio recordings *",
            type=["wav", "mp3", "flac", "ogg", "aiff", "aif"],
            accept_multiple_files=True,
            help=(
                "BirdNET will analyze each uploaded recording. "
                "WAV, MP3, FLAC and OGG are recommended."
            ),
        )
    else:
        audio_files = st.file_uploader(
            "Upload audio recordings (optional)",
            type=["wav", "mp3", "flac", "ogg", "aiff", "aif"],
            accept_multiple_files=True,
        )

    image_files = st.file_uploader(
        "Upload photographs (optional)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
    )

    notes = st.text_area(
        "Additional notes (optional)",
        placeholder=(
            "Colors, markings, weather, flock behavior, "
            "or other useful details."
        ),
    )

    st.subheader("3. Submission security")

    pin = st.text_input(
        "Submission PIN *",
        type="password",
        help="Enter the PIN provided by the database administrator.",
    )

    submitted = st.form_submit_button(
        "Submit bird observation",
        type="primary",
        use_container_width=True,
    )


# --------------------------------------------------
# Validate and process submission
# --------------------------------------------------

if submitted:
    expected_pin = st.secrets.get(
        "submission_pin",
        os.environ.get("submission_pin", ""),
    )

    if not expected_pin:
        st.error(
            "No submission PIN is configured. Ask the administrator "
            "to configure submission_pin in Streamlit secrets."
        )

    elif pin != expected_pin:
        st.error("Incorrect PIN. Your observation was not submitted.")

    elif not location.strip():
        st.error("Please enter the general location.")

    elif mode == "Audio identification" and not audio_files:
        st.error("Please upload at least one audio recording.")

    else:
        submission_id = str(uuid.uuid4())

        try:
            saved_audio = save_uploads(
                audio_files, AUDIO_DIR, submission_id
            )
            saved_images = save_uploads(
                image_files, IMAGE_DIR, submission_id
            )

            birdnet_results = []
            analysis_errors = []

            if mode == "Audio identification":
                try:
                    with st.spinner(
                        "Loading BirdNET and analyzing audio..."
                    ):
                        acoustic_model, geo_model = load_birdnet_model()

                        for relative_path in saved_audio:
                            absolute_path = PROJECT_DIR / relative_path

                            try:
                                predictions = identify_bird_audio(acoustic_model, geo_model, absolute_path)
                                
                                birdnet_results.append({
                                    "audio_file": relative_path,
                                    "predictions": predictions,
                                })
                            except Exception as error:
                                analysis_errors.append(
                                    f"{Path(relative_path).name}: {error}"
                                )

                except Exception as error:
                    analysis_errors.append(
                        f"BirdNET could not load: {error}"
                    )

            # In audio mode, species names come from BirdNET.
            if mode == "Audio identification":
                unique_species = []
                seen = set()

                for result in birdnet_results:
                    for prediction in result["predictions"]:
                        name = prediction["species"]
                        if name not in seen:
                            unique_species.append(name)
                            seen.add(name)

                final_bird_name = "; ".join(unique_species)
                if not final_bird_name:
                    final_bird_name = "Unknown"
            else:
                final_bird_name = bird_name.strip() or "Unknown"

            record = {
                "submission_id": submission_id,
                "submission_mode": mode,
                "bird_name": final_bird_name,
                "approximate_count": approximate_count,
                "location": location.strip(),
                "observation_date": observation_date.isoformat(),
                "observation_time": observation_time.strftime("%H:%M"),
                "image_files": ";".join(saved_images),
                "audio_files": ";".join(saved_audio),
                "birdnet_results": json.dumps(birdnet_results),
                "analysis_errors": "; ".join(analysis_errors),
                "notes": notes.strip(),
            }


            append_record(record)
            append_record2(record)

            st.success("Observation saved!")

            st.write("### Submission summary")
            st.write(f"**Submission ID:** `{submission_id}`")
            st.write(f"**Mode:** {mode}")
            st.write(f"**Bird name(s):** {final_bird_name}")
            st.write(f"**Location:** {location}")
            st.write(f"**Date:** {observation_date}")
            st.write(f"**Photos saved:** {len(saved_images)}")
            st.write(f"**Audio files saved:** {len(saved_audio)}")

            if birdnet_results:
                st.subheader("BirdNET identification results")

                for result in birdnet_results:
                    st.write(f"**Audio file:** {Path(result['audio_file']).name}")

                    if result["predictions"]:
                        display_rows = []
                        for prediction in result["predictions"]:
                            display_rows.append({
                                "Possible species": prediction["species"],
                                "Scientific name": prediction["scientific_name"],
                                "Model score": prediction["score"],
                            })

                        st.dataframe(
                            pd.DataFrame(display_rows),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.write("No species predictions were returned.")

                st.caption(
                    "BirdNET scores are model outputs, not guaranteed "
                    "probabilities that an identification is correct."
                )

            if analysis_errors:
                st.warning(
                    "The observation and uploaded files were saved, "
                    "but some audio analysis did not complete."
                )
                for error in analysis_errors:
                    st.write(f"- {error}")

            st.info(
                f"Local data folder: {DATA_DIR}\n\n"
                "Keep a backup of this folder. Local files may not persist "
                "if the app is deployed to some hosting platforms."
            )

        except Exception as error:
            st.error(
                "The submission could not be saved. "
                f"Details: {error}"
            )
