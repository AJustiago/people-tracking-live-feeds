# People Tracking CCTV System

This project is a **People Tracking CCTV System** that processes a live video feed to detect and track people within user-defined polygons, logs enter/leave events to MongoDB, and provides a REST API and web dashboard for data visualization. The system consists of four main components: a Tkinter-based GUI (`main.py`), a FastAPI backend (`api.py`), a Streamlit dashboard (`dashboard.py`), and a MongoDB handler (`mongo_utils.py`).

## Table of Contents
1. [System Overview](#system-overview)
2. [Database Design](#database-design)
3. [Design Considerations](#design-considerations)
4. [Local Setup Instructions](#local-setup-instructions)
5. [Usage](#usage)
6. [Dependencies](#dependencies)
7. [Future Improvements](#future-improvements)

## System Overview
The system performs the following functions:
- **Video Processing**: Captures a live CCTV feed, detects people using the YOLO-tiny model, and tracks their movement within user-defined polygons.
- **Polygon Management**: Allows users to draw, move, resize, and delete polygons via a Tkinter GUI, with configurations stored in MongoDB.
- **Event Logging**: Logs "enter" and "leave" events when people cross polygon boundaries, saved to MongoDB.
- **Data Access**: Provides a FastAPI backend with endpoints to retrieve historical and live statistics and configure polygons.
- **Visualization**: Displays historical and live data via a Streamlit dashboard with filtering and pagination.

## Database Design
The system uses MongoDB with two databases: `cctv_tracking` for polygon configurations and `people_tracking_logs` for event logs.

### Database Schema
- **Database**: `cctv_tracking`
  - **Collection**: `polygons`
    - `index`: Integer, unique identifier for the polygon (0-based).
    - `points`: Array of floats, representing polygon vertices as `[x1, y1, x2, y2, ...]` (constrained to 0-640 for x, 0-480 for y).
    - `isDeleted`: Boolean, indicates if the polygon is marked as deleted (soft deletion).
    - `updated_at`: UTC timestamp, records when the polygon was last updated.
    - Example Document:
      ```json
      {
        "index": 0,
        "points": [100.0, 100.0, 200.0, 100.0, 200.0, 200.0, 100.0, 200.0],
        "isDeleted": false,
        "updated_at": "2025-07-27T14:08:00Z"
      }
      ```
- **Database**: `people_tracking_logs`
  - **Collection**: `event_logs`
    - `person_id`: Integer, unique identifier for a tracked person.
    - `polygon_index`: Integer, references the polygon’s `index` from `cctv_tracking.polygons`.
    - `event_type`: String, either `"enter"` or `"leave"`.
    - `timestamp`: UTC timestamp, records when the event occurred.
    - Example Document:
      ```json
      {
        "person_id": 1,
        "polygon_index": 0,
        "event_type": "enter",
        "timestamp": "2025-07-27T14:08:00Z"
      }
      ```

### Database Diagram
Below is a simplified representation of the database schema using Mermaid syntax. You can render this using a Mermaid-compatible tool (e.g., GitHub, Mermaid Live Editor).

```mermaid
erDiagram
  cctv_tracking.polygons ||--o{ people_tracking_logs.event_logs : "references"
  cctv_tracking.polygons {
    int index
    float[] points
    boolean isDeleted
    datetime updated_at
  }
  people_tracking_logs.event_logs {
    int person_id
    int polygon_index
    string event_type
    datetime timestamp
  }
```

*Note*: Save the above Mermaid code as an image (e.g., `database_diagram.png`) using a tool like Mermaid Live Editor and embed it here:
![Database Diagram](path/to/database_diagram.png)

### Relationship Between Tables
- The `polygon_index` in `people_tracking_logs.event_logs` references the `index` in `cctv_tracking.polygons`, establishing a one-to-many relationship (one polygon can have multiple events).
- The relationship is not enforced by MongoDB (as it’s a NoSQL database), but the system ensures consistency by using `index` as a unique identifier for polygons.
- Soft deletion (`isDeleted: True`) in `polygons` ensures that historical event logs remain valid even if a polygon is deleted, as `event_logs` stores `polygon_index` independently.

## Design Considerations
### Video Input and Detection
- **Input**: The system uses a live CCTV stream from a public URL (`https://cctvjss.jogjakota.go.id/...`) via OpenCV in `main.py`.
- **Detection**:
  - The YOLO-tiny model (`hustvl/yolos-tiny`) from the Transformers library is used for human detection with a confidence threshold of 0.85.
  - Frames are resized to 640x480 pixels to match the canvas size and reduce computational load.
  - Person tracking uses a distance-based algorithm (`distance_threshold = 50` pixels, `max_missed_frames = 30`) to maintain person IDs across frames.
- **Processing**:
  - Video processing runs in a separate thread to avoid blocking the Tkinter GUI.
  - Frames are converted to Tkinter-compatible images using Pillow and displayed on a canvas.
- **Rationale**:
  - YOLO-tiny was chosen for its balance of speed and accuracy, suitable for real-time processing on modest hardware.
  - The distance-based tracking is simple yet effective for short-term tracking within a fixed camera view.
  - Threading ensures a responsive GUI while handling CPU-intensive tasks.

### Polygon and Event Log Relationship
- **Polygon Configuration**:
  - Polygons are defined by users via the Tkinter GUI (`main.py`) or API (`api.py`) and stored in `cctv_tracking.polygons`.
  - Each polygon has a unique `index` and a list of `points` (x, y coordinates), constrained to the 640x480 canvas.
  - Soft deletion (`isDeleted`) allows retaining historical data without affecting existing event logs.
- **Event Logging**:
  - When a person’s center point (from YOLO bounding box) enters or leaves a polygon (detected via ray-casting algorithm), an event is logged to `people_tracking_logs.event_logs`.
  - Events include `person_id`, `polygon_index`, `event_type` ("enter" or "leave"), and a UTC timestamp.
- **Rationale**:
  - The `index` field links `event_logs` to `polygons`, enabling efficient querying of events by polygon.
  - UTC timestamps ensure consistency across components, though `main.py` displays logs in WIB (Asia/Jakarta) for user readability.
  - Soft deletion prevents data loss and supports potential recovery of deleted polygons.

*Note*: Save the above Mermaid code as an image (e.g., `system_architecture.png`) and embed it here:
![System Architecture](path/to/system_architecture.png)

### Component Interactions
- **main.py**: Processes video, detects people, tracks them within polygons, and saves data to MongoDB via `MongoDBHandler`.
- **mongo_utils.py**: Provides a unified interface for MongoDB operations (polygon storage, event logging, data retrieval).
- **api.py**: Exposes RESTful endpoints (`/api/stats/`, `/api/stats/live`, `/api/config/area`) to query data and configure polygons.
- **dashboard.py**: Fetches data from `api.py` and visualizes it in a web-based dashboard with historical and live views.

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
   - Ensure `requirements.txt` includes:
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
   - Install MongoDB (e.g., MongoDB Community Server) if not already installed.
   - Start the MongoDB server:
     ```bash
     mongod
     ```
   - Verify the server is running on `localhost:27017` using a MongoDB client (e.g., MongoDB Compass).

4. **Install FFmpeg**:
   - Install FFmpeg for your OS (e.g., `apt-get install ffmpeg` on Ubuntu, `brew install ffmpeg` on macOS, or download from FFmpeg website for Windows).
   - Ensure FFmpeg is accessible in your system PATH.

### Running the Application
The system requires three components to run concurrently: the Tkinter GUI (`main.py`), the FastAPI server (`api.py`), and the Streamlit dashboard (`dashboard.py`). Open three terminal windows and activate the virtual environment in each.

1. **Run the FastAPI Server**:
   ```bash
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   python api.py
   ```
   - The server will run on `http://localhost:8000`.
   - Verify by accessing `http://localhost:8000/docs` in a browser to see the API documentation.

2. **Run the Tkinter GUI**:
   ```bash
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   python main.py
   ```
   - This opens a Tkinter window displaying the live CCTV feed.
   - Use the GUI to draw polygons, track people, and log events to MongoDB.
   - The video stream may take a few seconds to load depending on network conditions.

3. **Run the Streamlit Dashboard**:
   ```bash
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   streamlit run dashboard.py
   ```
   - The dashboard will open in your default browser at `http://localhost:8501`.
   - Use the dashboard to view historical and live statistics, filter by time range, and navigate paginated event logs.

### Notes
- Ensure MongoDB is running before starting any of the scripts.
- The CCTV stream URL in `main.py` (`https://cctvjss.jogjakota.go.id/...`) must be accessible. If it fails, replace it with another HLS stream URL or a local video file.
- Run the scripts in separate terminals to allow concurrent execution.
- If the dashboard shows "Failed to fetch stats" errors, verify that `api.py` is running and accessible at `http://localhost:8000`.

## Usage
- **Tkinter GUI (`main.py`)**:
  - Click "Add Polygon" to start drawing a polygon.
  - Left-click to add points, right-click to finish (minimum 3 points).
  - Drag polygons or vertices to move/resize; right-click a polygon to delete.
  - View action logs (e.g., "Person-1 entered Polygon-0") in the right panel.
  - Click "Help" for detailed instructions.
- **FastAPI Server (`api.py`)**:
  - Access `/api/stats/` to retrieve historical event logs and polygon statistics.
  - Access `/api/stats/live` for recent events (last 10 seconds) and current counts.
  - Use `/api/config/area` to configure polygons via POST requests (e.g., with `curl` or Postman).
- **Streamlit Dashboard (`dashboard.py`)**:
  - View historical event logs with time range filtering and pagination.
  - Monitor live statistics (updated every ~10 seconds) for recent events and current counts per polygon.

## Dependencies
The project relies on the following key dependencies (see `requirements.txt` for the full list):
- `opencv-python==4.12.0.88`: Video processing.
- `transformers==4.53.3`, `torch==2.7.1`: YOLO-tiny for human detection.
- `pymongo==4.13.2`: MongoDB interactions.
- `fastapi==0.116.1`, `uvicorn==0.35.0`: API server.
- `streamlit==1.47.0`, `pandas==2.3.1`: Dashboard visualization.
- `pillow==11.3.0`: Image handling for Tkinter.

## Future Improvements
- **Timezone Consistency**: Standardize timestamps to UTC or WIB across all components for display and filtering.
- **Charts**: Add Altair or Chart.js visualizations to `dashboard.py` for enter/leave counts or time series.
- **Polygon Configuration**: Integrate `/api/config/area` into `dashboard.py` for web-based polygon creation.
- **Error Handling**: Add retry logic for the CCTV stream and API requests.
- **Performance**: Optimize YOLO processing with GPU support or reduce frame processing frequency.
- **Dockerization**: Create a Docker Compose setup to simplify deployment and ensure consistent environments.