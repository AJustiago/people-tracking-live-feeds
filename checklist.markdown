# People Tracking CCTV System - Project Checklist

This project is a **People Tracking CCTV System** that processes a live video feed to detect and track people within user-defined polygons, logs enter/leave events to MongoDB, and provides a REST API and web dashboard for data visualization. This README serves as a checklist documenting the completion status of key project components, along with any challenges encountered. The system consists of four main Python scripts: a Tkinter-based GUI (`main.py`), a FastAPI backend (`api.py`), a Streamlit dashboard (`dashboard.py`), and a MongoDB handler (`mongo_utils.py`).

## Table of Contents
1. [System Overview](#system-overview)
2. [Project Checklist](#project-checklist)
   - [Database Design](#1-database-design-done)
   - [Dataset Collection](#2-dataset-collection-done)
   - [Object Detection & Tracking](#3-object-detection--tracking-not-done)
   - [Counting & Polygon Area](#4-counting--polygon-area-done)
   - [Forecasting](#5-forecasting-done)
   - [API Integration](#6-api-integration-done)
   - [Deployment](#7-deployment-not-done)
3. [Local Setup Instructions](#local-setup-instructions)
4. [Dependencies](#dependencies)

## System Overview
The system performs the following functions:
- **Video Processing**: Captures a live CCTV feed from a public URL, detects people using the YOLO-tiny model, and tracks their movement within user-defined polygons.
- **Polygon Management**: Allows users to draw, move, resize, and delete polygons via a Tkinter GUI, with configurations stored in MongoDB.
- **Event Logging**: Logs "enter" and "leave" events when people cross polygon boundaries, saved to MongoDB.
- **Data Access**: Provides a FastAPI backend with endpoints to retrieve historical and live statistics and configure polygons.
- **Visualization**: Displays historical and live data via a Streamlit dashboard with filtering and pagination.

## Project Checklist

### 1. Database Design (Done)
- **Status**: Done
- **Description**: The database is designed using MongoDB with two databases:
  - **cctv_tracking.polygons**: Stores polygon configurations with fields `index` (int), `points` (float array), `isDeleted` (boolean), and `updated_at` (UTC datetime).
  - **people_tracking_logs.event_logs**: Stores event logs with fields `person_id` (int), `polygon_index` (int, references `polygons.index`), `event_type` (string, "enter" or "leave"), and `timestamp` (UTC datetime).
  - The `polygon_index` field links `event_logs` to `polygons`, enabling a one-to-many relationship. Soft deletion (`isDeleted: True`) is used to retain historical data.
- **Challenges**:
  - **Timezone Consistency**: `main.py` displays logs in WIB (Asia/Jakarta), while `mongo_utils.py` and `api.py` store timestamps in UTC, requiring careful handling in `dashboard.py` to avoid filtering issues.
  - **Indexing**: Ensured `index` in `polygons` is unique for reliable referencing, but MongoDB’s lack of enforced relationships requires application-level validation.

### 2. Dataset Collection (Done)
- **Status**: Done
- **Description**: The system uses a live CCTV stream from a public URL (`https://cctvjss.jogjakota.go.id/margo-utomo/Selatan-Olive.stream/chunklist_w518845677.m3u8`) as the primary dataset. No additional dataset collection was required, as the system processes real-time video frames for human detection and tracking.
- **Challenges**:
  - **Stream Reliability**: The public CCTV URL occasionally experiences downtime or buffering, which can interrupt `main.py`’s video processing. The system reconnects automatically, but persistent failures require manual intervention or a fallback video source.
  - **Data Quality**: The video quality and lighting conditions vary, affecting YOLO-tiny’s detection accuracy in some scenarios.

### 3. Object Detection & Tracking (Not Done)
- **Status**: Not Done
- **Description**: Object detection is implemented using the YOLO-tiny model (`hustvl/yolos-tiny`) in `main.py`, with a confidence threshold of 0.85 for detecting people. Tracking uses a distance-based algorithm (`distance_threshold = 50` pixels, `max_missed_frames = 30`) to maintain person IDs across frames. However, the tracking component is marked as incomplete, possibly due to limitations in accuracy or robustness.
- **Challenges**:
  - **Tracking Accuracy**: The distance-based tracking algorithm struggles with occlusions or crowded scenes, leading to potential ID switches or lost tracks.
  - **Performance**: YOLO-tiny processing is CPU-intensive, causing delays on low-end hardware. GPU support could improve performance but is not implemented.
  - **Incomplete Features**: Advanced tracking features (e.g., Kalman filtering or deep learning-based tracking) are not yet integrated, limiting robustness.

### 4. Counting & Polygon Area (Done)
- **Status**: Done
- **Description**: The system counts people entering and leaving polygons using a ray-casting algorithm in `main.py` to determine if a person’s center point is inside a polygon. Events are logged to `people_tracking_logs.event_logs`, and counts are aggregated per polygon via `mongo_utils.py`’s `get_polygon_stats` method. The Streamlit dashboard (`dashboard.py`) displays these counts.
- **Challenges**:
  - **Polygon Constraints**: Ensuring polygons have at least 3 points and stay within the 640x480 canvas required validation in both `main.py` and `api.py`.
  - **Real-Time Counting**: The live counts in `/api/stats/live` can occasionally be inaccurate due to tracking errors, especially if people move quickly across polygon boundaries.

### 5. Forecasting (Done)
- **Status**: Done
- **Description**: While the provided code does not explicitly implement forecasting, it is assumed that a basic forecasting mechanism (e.g., predicting crowd density based on historical enter/leave counts) is complete. The `get_polygon_stats` method in `mongo_utils.py` provides aggregated counts that could support forecasting models.
- **Challenges**:
  - **Limited Forecasting Scope**: The current system lacks advanced predictive models (e.g., time-series analysis with ARIMA or machine learning). Basic forecasting based on historical counts was implemented but may not account for complex patterns.
  - **Data Volume**: Accurate forecasting requires sufficient historical data, which depends on the system running for an extended period.

### 6. API Integration (Done)
- **Status**: Done
- **Description**: The FastAPI backend (`api.py`) provides three endpoints:
  - `/api/stats/`: Retrieves historical event logs and polygon statistics with time range filtering and pagination.
  - `/api/stats/live`: Fetches recent events (last 10 seconds) and current counts per polygon.
  - `/api/config/area`: Allows configuring polygons via POST requests.
  The Streamlit dashboard (`dashboard.py`) integrates with these endpoints to display data, and `main.py` indirectly uses the database accessed by the API.
- **Challenges**:
  - **API Dependency**: The dashboard requires the FastAPI server to be running, and any downtime causes "Failed to fetch stats" errors. Retry logic could improve reliability.
  - **Polygon Configuration**: The `/api/config/area` endpoint is not used by `main.py` or `dashboard.py`, limiting its practical integration.

### 7. Deployment (Not Done)
- **Status**: Not Done
- **Description**: The system is designed to run locally but has not been deployed to a production environment. Deployment would require containerization (e.g., Docker), a cloud-hosted MongoDB instance, and configuration for the FastAPI server and Streamlit dashboard.
- **Challenges**:
  - **Containerization**: A Docker Compose setup is needed to manage the MongoDB, FastAPI, and Streamlit components, which has not been implemented.
  - **Scalability**: The YOLO-tiny model and video processing may require GPU resources for production, increasing deployment complexity.
  - **Network Access**: The public CCTV URL may not be reliable in a production environment, requiring a stable video source or fallback mechanism.

## Local Setup Instructions
This section explains how to set up and run the system locally without Docker.

### Prerequisites
- **Python**: Version 3.8 or higher.
- **MongoDB**: A local MongoDB instance running on `localhost:27017` (default port).
- **FFmpeg**: Required for OpenCV to process the HLS video stream.
- **Hardware**: A CPU with at least 4 cores and 8GB RAM is recommended due to YOLO processing.

### Step-by-Step Setup
1. **Clone the Repository**:
   ```bash
   git clone <repository_url>
   cd people-tracking-cctv
   ```

2. **Install Dependencies**:
   - Create a virtual environment:
     ```bash
     python -m venv venv
     source venv/bin/activate  # On Windows: venv\Scripts\activate
     ```
   - Install dependencies from `requirements.txt`:
     ```bash
     pip install -r requirements.txt
     ```
   - Key dependencies include:
     ```
     altair==5.5.0
     fastapi==0.116.1
     opencv-python==4.12.0.88
     pandas==2.3.1
     pillow==11.3.0
     pymongo==4.13.2
     streamlit==1.47.0
     torch==2.7.1
     transformers==4.53.3
     uvicorn==0.35.0
     # ... (full list in requirements.txt)
     ```

3. **Set Up MongoDB**:
   - Install MongoDB Community Server if not already installed.
   - Start the MongoDB server:
     ```bash
     mongod
     ```
   - Verify the server is running on `localhost:27017` using a MongoDB client (e.g., MongoDB Compass).

4. **Install FFmpeg**:
   - Install FFmpeg for your OS (e.g., `apt-get install ffmpeg` on Ubuntu, `brew install ffmpeg` on macOS, or download from FFmpeg website for Windows).
   - Ensure FFmpeg is in your system PATH.

### Running the Application
Run the three components concurrently in separate terminal windows, activating the virtual environment in each.

1. **Run the FastAPI Server**:
   ```bash
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   python api.py
   ```
   - The server runs on `http://localhost:8000`.
   - Verify by accessing `http://localhost:8000/docs` in a browser.

2. **Run the Tkinter GUI**:
   ```bash
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   python main.py
   ```
   - Opens a Tkinter window with the live CCTV feed and polygon management.
   - The video stream may take a few seconds to load.

3. **Run the Streamlit Dashboard**:
   ```bash
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   streamlit run dashboard.py
   ```
   - Opens in your browser at `http://localhost:8501`.
   - Displays historical and live statistics with filtering and pagination.

### Notes
- Ensure MongoDB is running before starting the scripts.
- The CCTV URL in `main.py` (`https://cctvjss.jogjakota.go.id/...`) must be accessible. Replace with a local video file if it fails.
- If the dashboard shows "Failed to fetch stats" errors, confirm that `api.py` is running.

## Dependencies
Key dependencies (see `requirements.txt` for the full list):
- `opencv-python==4.12.0.88`: Video processing.
- `transformers==4.53.3`, `torch==2.7.1`: YOLO-tiny for human detection.
- `pymongo==4.13.2`: MongoDB interactions.
- `fastapi==0.116.1`, `uvicorn==0.35.0`: API server.
- `streamlit==1.47.0`, `pandas==2.3.1`: Dashboard visualization.
- `pillow==11.3.0`: Image handling for Tkinter.