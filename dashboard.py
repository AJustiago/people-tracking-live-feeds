import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
import requests

# Streamlit page configuration
st.set_page_config(page_title="People Tracking Dashboard", layout="wide")

# API endpoints
API_BASE_URL = "http://localhost:8000"
STATS_URL = f"{API_BASE_URL}/api/stats/"
LIVE_STATS_URL = f"{API_BASE_URL}/api/stats/live"

# Initialize session state for pagination
if 'page' not in st.session_state:
    st.session_state.page = 1
if 'limit' not in st.session_state:
    st.session_state.limit = 10

def fetch_stats(start_time=None, end_time=None, page=1, limit=10):
    """Fetch historical stats from /api/stats/ with optional filters."""
    params = {"page": page, "limit": limit}
    if start_time:
        params["start_time"] = start_time.isoformat()
    if end_time:
        params["end_time"] = end_time.isoformat()
    
    try:
        response = requests.get(STATS_URL, params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Failed to fetch stats: {e}")
        return {"logs": [], "total": 0, "page": page, "limit": limit, "total_pages": 1, "polygon_counts": []}

def fetch_live_stats():
    """Fetch live stats from /api/stats/live."""
    try:
        response = requests.get(LIVE_STATS_URL, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Failed to fetch live stats: {e}")
        return {"logs": [], "current_counts": {}}

# Dashboard layout
st.title("People Tracking Dashboard")

# Two-column layout
col1, col2 = st.columns([2, 1])

# Column 1: Historical Stats
with col1:
    st.header("Historical Statistics")
    
    # Time range filters
    st.subheader("Filter by Time Range (UTC)")
    time_col1, time_col2 = st.columns(2)
    with time_col1:
        start_time_str = st.text_input("Start Time (YYYY-MM-DD HH:MM:SS UTC)", "2025-07-23 00:00:00")
    with time_col2:
        end_time_str = st.text_input("End Time (YYYY-MM-DD HH:MM:SS UTC)", "2025-07-23 23:59:59")
    
    # Parse time inputs
    try:
        start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.UTC)
    except ValueError:
        start_time = None
        st.warning("Invalid start time format. Using no start time filter.")
    
    try:
        end_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.UTC)
    except ValueError:
        end_time = None
        st.warning("Invalid end time format. Using no end time filter.")
    
    # Pagination controls
    st.subheader("Pagination")
    page_col1, page_col2 = st.columns(2)
    with page_col1:
        if st.button("Previous Page") and st.session_state.page > 1:
            st.session_state.page -= 1
    with page_col2:
        if st.button("Next Page"):
            st.session_state.page += 1
    limit = st.selectbox("Records per page", [10, 25, 50, 100], index=0)
    st.session_state.limit = limit
    
    # Fetch and display historical stats
    stats = fetch_stats(start_time, end_time, st.session_state.page, st.session_state.limit)
    logs = stats.get("logs", [])
    total = stats.get("total", 0)
    page = stats.get("page", 1)
    total_pages = stats.get("total_pages", 1)
    polygon_counts = stats.get("polygon_counts", [])
    
    # Display event logs table
    st.subheader("Event Logs")
    if logs:
        try:
            df = pd.DataFrame(logs)
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                df = df[["person_id", "polygon_index", "event_type", "timestamp"]]
                df.columns = ["Person ID", "Polygon Index", "Event Type", "Timestamp"]
                st.dataframe(df, use_container_width=True)
                st.write(f"Page {page} of {total_pages} | Total Records: {total}")
            else:
                st.error("Timestamp field missing in event logs.")
        except Exception as e:
            st.error(f"Failed to process event logs: {e}")
    else:
        st.write("No historical event logs available.")
    
    # Display polygon counts table
    st.subheader("Enter/Leave Counts per Polygon")
    if polygon_counts:
        counts_df = pd.DataFrame(polygon_counts)
        counts_df = counts_df[["polygon_index", "enter_count", "leave_count"]]
        counts_df.columns = ["Polygon Index", "Enter Count", "Leave Count"]
        st.dataframe(counts_df, use_container_width=True)
    else:
        st.write("No polygon count data available.")

# Column 2: Live Stats
with col2:
    st.header("Live Statistics")
    
    # Auto-refresh live stats
    live_stats_placeholder = st.empty()
    with live_stats_placeholder.container():
        live_stats = fetch_live_stats()
        logs = live_stats.get("logs", [])
        current_counts = live_stats.get("current_counts", {})
        
        # Display live stats table
        if logs:
            try:
                df = pd.DataFrame(logs)
                if "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                    df = df[["person_id", "polygon_index", "event_type", "timestamp"]]
                    df.columns = ["Person ID", "Polygon Index", "Event Type", "Timestamp"]
                    st.subheader("Recent Events (Last 10 Seconds)")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.error("Timestamp field missing in live event logs.")
            except Exception as e:
                st.error(f"Failed to process live event logs: {e}")
        
        # Display current counts
        if current_counts:
            counts_df = pd.DataFrame(
                [(k, v) for k, v in current_counts.items()],
                columns=["Polygon Index", "Current Count"]
            )
            st.subheader("Current People in Polygons")
            st.dataframe(counts_df, use_container_width=True)
        else:
            st.write("No live data available.")

# Auto-refresh live stats every 5 seconds
st_autorefresh = st.session_state.get("st_autorefresh", 0)
if st_autorefresh % 50 == 0:  # Approx. 5 seconds (Streamlit runs at ~10Hz)
    live_stats_placeholder.empty()
    with live_stats_placeholder.container():
        live_stats = fetch_live_stats()
        logs = live_stats.get("logs", [])
        current_counts = live_stats.get("current_counts", {})
        
        if logs:
            try:
                df = pd.DataFrame(logs)
                if "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                    df = df[["person_id", "polygon_index", "event_type", "timestamp"]]
                    df.columns = ["Person ID", "Polygon Index", "Event Type", "Timestamp"]
                    st.subheader("Recent Events (Last 10 Seconds)")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.error("Timestamp field missing in live event logs.")
            except Exception as e:
                st.error(f"Failed to process live event logs: {e}")
        
        if current_counts:
            counts_df = pd.DataFrame(
                [(k, v) for k, v in current_counts.items()],
                columns=["Polygon Index", "Current Count"]
            )
            st.subheader("Current People in Polygons")
            st.dataframe(counts_df, use_container_width=True)
        else:
            st.write("No live data available.")
st.session_state.st_autorefresh = st_autorefresh + 1