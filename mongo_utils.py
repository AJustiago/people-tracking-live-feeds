from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz
from typing import Optional

class MongoDBHandler:
    def __init__(self, host='localhost', port=27017, polygon_db_name='cctv_tracking', log_db_name='people_tracking_logs', polygon_collection_name='polygons', log_collection_name='event_logs'):
        """Initialize MongoDB connections for polygons and event logs."""
        try:
            self.client = MongoClient(f'mongodb://{host}:{port}/', serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')  # Test connection
            self.polygon_db = self.client[polygon_db_name]
            self.polygon_collection = self.polygon_db[polygon_collection_name]
            self.log_db = self.client[log_db_name]
            self.log_collection = self.log_db[log_collection_name]
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MongoDB: {e}")

    def load_polygons(self):
        """Load non-deleted polygons from MongoDB, sorted by index."""
        return list(self.polygon_collection.find({"isDeleted": False}).sort("index", 1))

    def save_polygon(self, index, points):
        """Save or update a polygon in MongoDB with isDeleted set to False."""
        try:
            self.polygon_collection.update_one(
                {'index': index},
                {'$set': {
                    'points': points,
                    'isDeleted': False,
                    'updated_at': datetime.now(pytz.UTC)
                }},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"Failed to save polygon {index}: {e}")
            return False

    def delete_polygon(self, index):
        """Mark a polygon as deleted in MongoDB by setting isDeleted to True."""
        try:
            self.polygon_collection.update_one(
                {'index': index},
                {'$set': {
                    'isDeleted': True,
                    'updated_at': datetime.now(pytz.UTC)
                }}
            )
        except Exception as e:
            print(f"Failed to delete polygon {index}: {e}")

    def mark_all_polygons_deleted(self):
        """Mark all polygons as deleted in MongoDB by setting isDeleted to True."""
        try:
            self.polygon_collection.update_many(
                {},
                {'$set': {
                    'isDeleted': True,
                    'updated_at': datetime.now(pytz.UTC)
                }}
            )
        except Exception as e:
            print(f"Failed to mark all polygons as deleted: {e}")

    def save_event_log(self, person_id, polygon_index, event_type):
        """Save an enter/leave event to the event_logs collection."""
        try:
            self.log_collection.insert_one({
                'person_id': person_id,
                'polygon_index': polygon_index,
                'event_type': event_type,
                'timestamp': datetime.now(pytz.UTC)
            })
            return True
        except Exception as e:
            print(f"Failed to save event log for Person-{person_id} {event_type} Polygon-{polygon_index}: {e}")
            return False
        
    def get_event_logs(self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None, page: int = 1, limit: int = 100):
        """Retrieve event logs with optional time range and pagination."""
        query = {}
        if start_time and end_time:
            if start_time >= end_time:
                raise ValueError("start_time must be before end_time")
            query["timestamp"] = {"$gte": start_time, "$lte": end_time}
        elif start_time:
            query["timestamp"] = {"$gte": start_time}
        elif end_time:
            query["timestamp"] = {"$lte": end_time}
        
        skip = (page - 1) * limit
        logs = list(self.log_collection.find(query).sort("timestamp", -1).skip(skip).limit(limit))
        total = self.log_collection.count_documents(query)
        
        return logs, total

    def get_live_events(self, seconds: int = 10):
        """Retrieve events from the last N seconds."""
        threshold = datetime.now(pytz.UTC) - timedelta(seconds=seconds)
        query = {"timestamp": {"$gte": threshold}}
        logs = list(self.log_collection.find(query).sort("timestamp", -1))
        return logs

    def get_polygon_stats(self, start_time: Optional[datetime] = None, end_time: Optional[datetime] = None):
        """Retrieve enter/leave counts per polygon with optional time range."""
        query = {}
        if start_time and end_time:
            if start_time >= end_time:
                raise ValueError("start_time must be before end_time")
            query["timestamp"] = {"$gte": start_time, "$lte": end_time}
        elif start_time:
            query["timestamp"] = {"$gte": start_time}
        elif end_time:
            query["timestamp"] = {"$lte": end_time}
        
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": {"polygon_index": "$polygon_index", "event_type": "$event_type"},
                "count": {"$sum": 1}
            }},
            {"$group": {
                "_id": "$_id.polygon_index",
                "stats": {
                    "$push": {
                        "event_type": "$_id.event_type",
                        "count": "$count"
                    }
                }
            }},
            {"$sort": {"_id": 1}}
        ]
        results = list(self.log_collection.aggregate(pipeline))
        
        stats = []
        for result in results:
            polygon_index = result["_id"]
            enter_count = 0
            leave_count = 0
            for stat in result["stats"]:
                if stat["event_type"] == "enter":
                    enter_count = stat["count"]
                elif stat["event_type"] == "leave":
                    leave_count = stat["count"]
            stats.append({
                "polygon_index": polygon_index,
                "enter_count": enter_count,
                "leave_count": leave_count
            })
        
        return stats

    def close(self):
        """Close the MongoDB connection."""
        self.client.close()