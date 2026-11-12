
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "wildlife_data"
CSV_FILE = DATA_DIR / "submissions.csv"
CSV_FILE2 = DATA_DIR / "submissions2.csv"
media_dir = PROJECT_DIR / "wildlife_data"

st.title("Wildlife Database Administration")
st.write("Administrator access only.")

# Require the administrator PIN.
if "admin_authenticated" not in st.session_state:
    st.session_state["admin_authenticated"] = False

if not st.session_state["admin_authenticated"]:
    entered_pin = st.text_input(
        "Administrator PIN",
        type="password",
    )

    if st.button("Unlock administrator page"):
        if entered_pin == str(st.secrets["admin_pin"]):
            st.session_state["admin_authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect PIN.")

    st.stop()

if not CSV_FILE.is_file():
    st.info("There are no saved observations to manage yet.")
    st.stop()

try:
    df = pd.read_csv(CSV_FILE, keep_default_na=False)
except Exception:
    st.error("The submissions file could not be read. No changes were made.")
    st.stop()

if df.empty:
    st.info("There are no observations to manage yet.")
    st.stop()

# Show a short summary so the administrator can select a record.
def observation_label(row_id):
    row = df.loc[row_id]
    return (
        f"{row.get('bird_name', 'Unknown species')} | "
        f"{row.get('observation_date', 'Unknown date')} | "
        f"{row.get('location', 'Unknown location')} | "
        f"Record {row_id + 1}"
    )

if CSV_FILE2.exists():
    with open(CSV_FILE2, "rb") as file:
        st.download_button(
            label="Download Formatted CSV",
            data=file,
            file_name="submissions.csv",
            mime="text/csv",
        )
else:
    st.info("No database file found yet. Submit an observation to create it!")

st.subheader("Saved observations")
st.dataframe(
    df[
        [
            col for col in [
                "bird_name",
                "observation_date",
                "observation_time",
                "location",
                "submission_id",
                "notes",
            ]
            if col in df.columns
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

st.warning(
    "Deleting a record permanently removes it from the CSV. "
    "This page does not automatically delete attached photos or audio."
)

selected_id = st.selectbox(
    "Choose the observation to remove",
    options=df.index.tolist(),
    format_func=observation_label,
)

selected = df.loc[selected_id]
st.write("**Selected species:**", selected.get("bird_name", "Unknown"))
st.write("**Date:**", selected.get("observation_date", "Unknown"))
st.write("**Location:**", selected.get("location", "Unknown"))
st.write("**Audio Recordings:**")

audio_files = str(
    df.loc[selected_id].get("audio_files", "") or ""
)

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



confirm_delete = st.checkbox(
    "I have checked this record and want to permanently delete it."
)

if st.button("Delete selected observation", type="primary"):
    if not confirm_delete:
        st.error("Please check the confirmation box first.")
    else:
        # Preserve the original file before changing it.
        backup_file = DATA_DIR / "submissions_backup.csv"

        try:
            if not backup_file.exists():
                df.to_csv(backup_file, index=False, encoding="utf-8")

            remaining = df.drop(index=selected_id)
            temp_file = DATA_DIR / "submissions_temp.csv"
            remaining.to_csv(
                temp_file,
                index=False,
                encoding="utf-8",
            )
            temp_file.replace(CSV_FILE)

            st.success("Observation deleted successfully.")
            st.rerun()
        except Exception as error:
            st.error(f"Deletion failed. Check the file permissions. Details: {error}")

if st.button("Lock administrator page"):
    st.session_state["admin_authenticated"] = False
    st.rerun()
    