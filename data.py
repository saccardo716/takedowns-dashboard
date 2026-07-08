import os
from datetime import datetime, timedelta

import gspread
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2.service_account import Credentials

SHEET_ID = "1maI0JLyNGYxGvKugEsd97VLzcdf5txbCQoW23gcFBQ0"
TAB_NAME = "Sheet1"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/bigquery",
]

PRIORITY_THRESHOLDS = [
    (100_000, "Critical"),
    (10_000, "High"),
    (1_000, "Medium"),
    (0, "Low"),
]


def _get_credentials():
    key_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "")
    if key_path and os.path.isfile(key_path):
        return Credentials.from_service_account_file(key_path, scopes=SCOPES)
    if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    return Credentials.from_service_account_file(
        os.path.expanduser("~/.config/gcloud/service_account.json"), scopes=SCOPES
    )


def _bq_client():
    return bigquery.Client(credentials=_get_credentials())


def _get_priority(global_streams: int) -> str:
    for threshold, label in PRIORITY_THRESHOLDS:
        if global_streams >= threshold:
            return label
    return "Low"


@st.cache_data(ttl=900, show_spinner="Loading sheet data…")
def load_sheet_data() -> pd.DataFrame:
    creds = _get_credentials()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(TAB_NAME)
    records = ws.get_all_values()

    if len(records) < 2:
        return pd.DataFrame()

    rows = []
    for row in records[1:]:
        uri = str(row[0]).strip()
        if not uri:
            continue
        track_id = uri.replace("spotify:track:", "") if uri.startswith("spotify:track:") else uri
        rows.append(
            {
                "uri": uri,
                "track_id": track_id,
                "title": str(row[1]).strip(),
                "artists": str(row[2]).strip(),
                "label": str(row[3]).strip(),
                "licensor": str(row[4]).strip(),
                "earliest_live_date": str(row[5]).strip(),
                "publishers_lacking_clearance": str(row[6]).strip(),
                "date_added": str(row[7]).strip(),
            }
        )

    return pd.DataFrame(rows)


@st.cache_data(ttl=3600, show_spinner="Fetching MV stream counts…")
def load_mv_streams(_uris: tuple[str, ...]) -> dict[str, int]:
    if not _uris:
        return {}

    uris_list = list(_uris)
    client = _bq_client()

    query = """
        SELECT
          s.track_uri,
          COUNT(*) AS global_streams
        FROM `content-analytics-prod.music_videos.logic_music_video_user_streams_daily` s
        WHERE s.date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 92 DAY)
                          AND DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY)
          AND s.track_uri IN UNNEST(@uris)
          AND NOT s.is_preview
          AND s.provider_top_type NOT IN ('watch_feed', 'audiobrowse')
          AND s.is_stream_30s
        GROUP BY 1
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("uris", "STRING", uris_list),
        ]
    )

    result = client.query(query, job_config=job_config).result()
    return {row.track_uri: row.global_streams for row in result}


def _resolve_availability_table(client: bigquery.Client) -> str:
    for days_ago in range(1, 4):
        dt = datetime.utcnow() - timedelta(days=days_ago)
        suffix = dt.strftime("%Y%m%d")
        table_id = f"content-platform-pi.content_availability.track_availability_{suffix}"
        try:
            client.get_table(table_id)
            return table_id
        except Exception:
            continue
    raise RuntimeError("No recent track_availability partition found (checked last 3 days).")


@st.cache_data(ttl=3600, show_spinner="Checking US availability…")
def load_us_availability(_uris: tuple[str, ...]) -> dict[str, bool]:
    if not _uris:
        return {}

    uris_list = list(_uris)
    client = _bq_client()
    table_id = _resolve_availability_table(client)

    query = f"""
        SELECT
          track_uri,
          is_available_in_us
        FROM `{table_id}`
        WHERE track_uri IN UNNEST(@uris)
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("uris", "STRING", uris_list),
        ]
    )

    result = client.query(query, job_config=job_config).result()
    return {row.track_uri: row.is_available_in_us for row in result}


def load_all_data() -> pd.DataFrame:
    df = load_sheet_data()
    if df.empty:
        return df

    uris = tuple(u for u in df["uri"].tolist() if u.startswith("spotify:track:"))

    streams = {}
    us_avail = {}
    try:
        streams = load_mv_streams(uris)
    except Exception as e:
        st.warning(f"Could not load MV stream data: {e}")
    try:
        us_avail = load_us_availability(uris)
    except Exception as e:
        st.warning(f"Could not load US availability data: {e}")

    df["global_streams"] = df["uri"].map(streams).fillna(0).astype(int)
    df["priority"] = df["global_streams"].apply(_get_priority)
    df["us_available"] = df["uri"].map(us_avail)

    return df
