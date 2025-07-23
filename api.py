from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
import pytz
from fastapi.responses import JSONResponse
from mongo_utils import MongoDBHandler

# Initialize FastAPI app with Swagger metadata
app = FastAPI(
    title="People Tracking API",
    description="API for retrieving people tracking statistics and configuring detection polygons.",
    version="1.0.0"
)

# Pydantic models for request/response validation
class Point(BaseModel):
    x: float = Field(..., ge=0, le=640, description="X-coordinate within canvas (0-640)")
    y: float = Field(..., ge=0, le=480, description="Y-coordinate within canvas (0-480)")

class PolygonConfig(BaseModel):
    index: int = Field(..., ge=0, description="Unique polygon index")
    points: List[Point] = Field(..., min_items=3, description="List of at least 3 points defining the polygon")

class EventLog(BaseModel):
    person_id: int
    polygon_index: int
    event_type: str
    timestamp: str  # Changed to str to match ISO 8601 string

class PolygonStats(BaseModel):
    polygon_index: int
    enter_count: int
    leave_count: int

class StatsResponse(BaseModel):
    logs: List[EventLog]
    total: int
    page: int
    limit: int
    total_pages: int
    polygon_counts: List[PolygonStats]

class LiveStatsResponse(BaseModel):
    logs: List[EventLog]
    current_counts: dict

# Custom serialization for MongoDB documents
def serialize_mongo_doc(doc):
    """Convert MongoDB document to JSON-serializable format."""
    if isinstance(doc, list):
        return [serialize_mongo_doc(item) for item in doc]
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, (dict, list)):
                result[key] = serialize_mongo_doc(value)
            else:
                result[key] = value
        return result
    return doc

# Initialize MongoDB handler
try:
    mongo_handler = MongoDBHandler()
except ConnectionError as e:
    raise Exception(f"Failed to initialize MongoDB: {e}")

@app.on_event("shutdown")
def shutdown_event():
    mongo_handler.close()

@app.get("/api/stats/", response_model=StatsResponse, summary="Get historical people tracking statistics")
async def get_stats(
    start_time: Optional[datetime] = Query(None, description="Start time for filtering logs (ISO 8601, e.g., 2025-07-23T14:30:00Z)"),
    end_time: Optional[datetime] = Query(None, description="End time for filtering logs (ISO 8601, e.g., 2025-07-23T14:30:00Z)"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Number of logs per page")
):
    """
    Retrieve historical counts of people entering/leaving polygons, including per-polygon enter/leave counts.
    
    - **start_time**: Optional start time for filtering (UTC).
    - **end_time**: Optional end time for filtering (UTC).
    - **page**: Page number for pagination (default: 1).
    - **limit**: Number of records per page (default: 100, max: 1000).
    
    Returns a list of event logs, total count, pagination details, and enter/leave counts per polygon.
    """
    try:
        # Fetch event logs
        logs, total = mongo_handler.get_event_logs(start_time, end_time, page, limit)
        total_pages = (total + limit - 1) // limit
        
        # Fetch polygon enter/leave counts
        polygon_counts = mongo_handler.get_polygon_stats(start_time, end_time)
        
        # Serialize logs to convert timestamps to ISO 8601 strings
        serialized_logs = serialize_mongo_doc(logs)
        
        return JSONResponse(
            content={
                "logs": serialized_logs,
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "polygon_counts": polygon_counts
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve stats: {e}")

@app.get("/api/stats/live", response_model=LiveStatsResponse, summary="Get live people tracking statistics")
async def get_live_stats():
    """
    Retrieve the latest enter/leave events (last 10 seconds) and current counts of people in each polygon.
    
    Returns recent event logs and a dictionary of current people counts per polygon.
    """
    try:
        logs = mongo_handler.get_live_events(seconds=10)
        current_counts = {}
        for log in logs:
            polygon_index = log["polygon_index"]
            event_type = log["event_type"]
            if polygon_index not in current_counts:
                current_counts[polygon_index] = 0
            if event_type == "enter":
                current_counts[polygon_index] += 1
            elif event_type == "leave":
                current_counts[polygon_index] -= 1
            current_counts[polygon_index] = max(0, current_counts[polygon_index])
        
        # Serialize logs to convert timestamps to ISO 8601 strings
        serialized_logs = serialize_mongo_doc(logs)
        
        return JSONResponse(
            content={
                "logs": serialized_logs,
                "current_counts": current_counts
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve live stats: {e}")

@app.post("/api/config/area", summary="Configure a polygon area")
async def config_area(config: PolygonConfig):
    """
    Configure a polygon area by specifying its index and coordinates.
    
    - **index**: Unique integer identifier for the polygon.
    - **points**: List of at least 3 points (x, y) defining the polygon, within canvas bounds (x: 0-640, y: 0-480).
    
    Returns a success message if the polygon is saved.
    """
    try:
        points = [coord for point in config.points for coord in [point.x, point.y]]
        if len(points) < 6 or len(points) % 2 != 0:
            raise ValueError("Polygon must have at least 3 points (6 coordinates)")
        
        if mongo_handler.save_polygon(config.index, points):
            return {"message": f"Polygon-{config.index} configured successfully with {len(points)//2} vertices"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to save Polygon-{config.index}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to configure polygon: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)