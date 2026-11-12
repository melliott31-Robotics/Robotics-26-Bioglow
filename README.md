
# St. Louis Project Wildlife Database

A Streamlit application for recording and reviewing wildlife observations in the St. Louis area.

## Features

- Submit bird observations manually
- Identify bird species from audio using BirdNET
- Save observation details and identification scores
- Browse wildlife records

## Setup

1. Install Python 3.13.
2. Install the dependencies:

   `python -m pip install -r requirements.txt`

3. Configure the submission PIN in `.streamlit/secrets.toml`.
4. Start the application:

   `python -m streamlit run "Home Page.py"`

## Data and privacy

Local observations, recordings, and secrets are excluded from the Git repository.
