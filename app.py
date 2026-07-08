import streamlit as st
import pandas as pd
from data import load_all_data, SHEET_ID

st.set_page_config(
    page_title="Clearance Removal Dashboard",
    page_icon="🎵",
    layout="wide",
)

PRIORITY_COLORS = {
    "Critical": "#E91429",
    "High": "#F59B23",
    "Medium": "#F5D623",
    "Low": "#B3B3B3",
}

SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"

st.markdown(
    """
    <style>
    /* tighten top padding */
    .block-container { padding-top: 1.5rem; }
    /* header bar */
    .dashboard-header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 0 20px 0;
        border-bottom: 1px solid #3a3a3a;
        margin-bottom: 20px;
    }
    .dashboard-header h1 {
        font-size: 22px;
        font-weight: 700;
        margin: 0;
        color: #FFFFFF;
    }
    .dashboard-header .subtitle {
        font-size: 12px;
        color: #B3B3B3;
        margin-top: 2px;
    }
    /* priority badges */
    .priority-critical { color: #E91429; }
    .priority-high { color: #F59B23; }
    .priority-medium { color: #F5D623; }
    .priority-low { color: #B3B3B3; }
    /* metric cards */
    [data-testid="stMetric"] {
        background: #1E1E1E;
        border: 1px solid #3a3a3a;
        border-radius: 10px;
        padding: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Header ────────────────────────────────────────────────────
st.markdown(
    """
    <div class="dashboard-header">
        <svg viewBox="0 0 24 24" fill="#1DB954" width="28" height="28" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm4.586 14.424a.622.622 0 01-.857.207c-2.348-1.435-5.304-1.76-8.785-.963a.622.622 0 01-.277-1.215c3.809-.87 7.077-.496 9.712 1.115.294.18.386.563.207.856zm1.223-2.722a.779.779 0 01-1.072.257c-2.687-1.652-6.785-2.131-9.965-1.166a.78.78 0 01-.973-.519.781.781 0 01.518-.973c3.632-1.102 8.147-.568 11.234 1.329a.78.78 0 01.258 1.072zm.105-2.835C14.692 8.95 9.375 8.775 6.297 9.71a.937.937 0 11-.543-1.793c3.563-1.08 9.484-.872 13.22 1.327a.937.937 0 01-.06 1.623z"/>
        </svg>
        <div>
            <h1>Clearance Removal Notifications</h1>
            <div class="subtitle">Clearance &amp; Visibility Dashboard</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"[Open Google Sheet]({SHEET_URL})")
    if st.button("Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Load data ─────────────────────────────────────────────────
df = load_all_data()

if df.empty:
    st.info("No data found in the spreadsheet.")
    st.stop()

# ── Sidebar filters ──────────────────────────────────────────
with st.sidebar:
    st.divider()
    search = st.text_input("Search", placeholder="Title, artist, URI…")

    licensors = sorted(df["licensor"].dropna().unique())
    selected_licensors = st.multiselect("Licensor", licensors)

    publishers = sorted(df["publishers_lacking_clearance"].dropna().unique())
    selected_publishers = st.multiselect("Publisher Lacking Clearance", publishers)

    priorities = ["Critical", "High", "Medium", "Low"]
    selected_priorities = st.multiselect("Priority", priorities)

    us_filter = st.radio(
        "US Availability",
        ["All", "Available", "Blocked"],
        horizontal=True,
    )

# ── Apply filters ─────────────────────────────────────────────
filtered = df.copy()

if search:
    search_lower = search.lower()
    mask = (
        filtered["title"].str.lower().str.contains(search_lower, na=False)
        | filtered["artists"].str.lower().str.contains(search_lower, na=False)
        | filtered["uri"].str.lower().str.contains(search_lower, na=False)
        | filtered["label"].str.lower().str.contains(search_lower, na=False)
        | filtered["licensor"].str.lower().str.contains(search_lower, na=False)
    )
    filtered = filtered[mask]

if selected_licensors:
    filtered = filtered[filtered["licensor"].isin(selected_licensors)]

if selected_publishers:
    filtered = filtered[filtered["publishers_lacking_clearance"].isin(selected_publishers)]

if selected_priorities:
    filtered = filtered[filtered["priority"].isin(selected_priorities)]

if us_filter == "Available":
    filtered = filtered[filtered["us_available"] == True]  # noqa: E712
elif us_filter == "Blocked":
    filtered = filtered[filtered["us_available"] == False]  # noqa: E712

# ── Summary metrics ───────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Assets", f"{len(filtered):,}")
col2.metric("Critical", f"{(filtered['priority'] == 'Critical').sum():,}")
col3.metric("High", f"{(filtered['priority'] == 'High').sum():,}")
col4.metric("Medium + Low", f"{((filtered['priority'] == 'Medium') | (filtered['priority'] == 'Low')).sum():,}")

# ── Prepare display DataFrame ─────────────────────────────────
display_df = filtered[
    [
        "uri",
        "title",
        "artists",
        "global_streams",
        "priority",
        "us_available",
        "label",
        "licensor",
        "earliest_live_date",
        "publishers_lacking_clearance",
        "date_added",
    ]
].copy()

display_df["open_link"] = display_df["uri"].apply(
    lambda u: f"https://open.spotify.com/track/{u.replace('spotify:track:', '')}"
    if u.startswith("spotify:track:")
    else None
)

display_df["us_available"] = display_df["us_available"].map(
    {True: "Available", False: "Blocked", None: "--"}
)

display_df = display_df.sort_values("global_streams", ascending=False).reset_index(drop=True)

# ── Data table ────────────────────────────────────────────────
st.dataframe(
    display_df,
    column_config={
        "open_link": st.column_config.LinkColumn(
            "Open",
            display_text="▶",
            width="small",
        ),
        "uri": st.column_config.TextColumn("Spotify URI", width="medium"),
        "title": st.column_config.TextColumn("Title", width="medium"),
        "artists": st.column_config.TextColumn("Artist", width="medium"),
        "global_streams": st.column_config.NumberColumn(
            "Global MV Streams (90d)",
            format="%d",
        ),
        "priority": st.column_config.TextColumn("Priority", width="small"),
        "us_available": st.column_config.TextColumn("US", width="small"),
        "label": st.column_config.TextColumn("Label"),
        "licensor": st.column_config.TextColumn("Licensor"),
        "earliest_live_date": st.column_config.TextColumn("Earliest Live Date"),
        "publishers_lacking_clearance": st.column_config.TextColumn("Publishers Lacking Clearance"),
        "date_added": st.column_config.TextColumn("Date Added"),
    },
    column_order=[
        "open_link",
        "uri",
        "title",
        "artists",
        "global_streams",
        "priority",
        "us_available",
        "label",
        "licensor",
        "earliest_live_date",
        "publishers_lacking_clearance",
        "date_added",
    ],
    hide_index=True,
    use_container_width=True,
    height=700,
)

# ── Download button ───────────────────────────────────────────
with st.sidebar:
    st.divider()
    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered CSV",
        csv,
        "clearance_removal_filtered.csv",
        "text/csv",
        use_container_width=True,
    )
    st.caption(f"{len(filtered):,} of {len(df):,} assets shown")
