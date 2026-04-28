import os
import socket
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

# MongoDB connection details
MONGO_URI = "mongodb+srv://dbmatloob:222007matloob@cluster0.trwuj2z.mongodb.net/?appName=Cluster0"
DB_NAME = "matloob_scraper"

class MongoDBManager:
    """Manages tracking user activity and scraped lead counts in MongoDB."""
    
    def __init__(self):
        self.client = None
        self.db = None
        self.computer_name = socket.gethostname()
        self._connected = False

    def connect(self):
        """Establish connection to MongoDB."""
        try:
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            # Simple check to verify connection
            self.client.admin.command('ismaster')
            self.db = self.client[DB_NAME]
            self._connected = True
            return True
        except (ConnectionFailure, OperationFailure) as e:
            print(f"MongoDB Connection Error: {e}")
            self._connected = False
            return False

    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self._connected = False

    def track_start(self, source: str, url: str):
        """Record the start of a scraping session."""
        if not self._connected and not self.connect():
            return None
            
        activity = {
            "computer_name": self.computer_name,
            "source": source,
            "target_url": url,
            "start_time": datetime.now(),
            "status": "running",
            "emails_found": 0,
            "last_updated": datetime.now()
        }
        
        try:
            result = self.db.user_activity.insert_one(activity)
            return result.inserted_id
        except Exception as e:
            print(f"Error tracking start in MongoDB: {e}")
            return None

    def update_activity(self, activity_id: Any, emails_count: int, status: str = "running"):
        """Update the email count for an active session."""
        if not self._connected or activity_id is None:
            return
            
        try:
            self.db.user_activity.update_one(
                {"_id": activity_id},
                {
                    "$set": {
                        "emails_found": emails_count,
                        "status": status,
                        "last_updated": datetime.now()
                    }
                }
            )
        except Exception as e:
            print(f"Error updating MongoDB activity: {e}")

    def get_user_stats(self):
        """Get stats for the current computer, including bill."""
        if not self._connected and not self.connect():
            return {"total_emails": 0, "total_sessions": 0, "bill_pkr": 0.0}
            
        try:
            pipeline = [
                {"$match": {"computer_name": self.computer_name}},
                {"$group": {
                    "_id": "$computer_name",
                    "total_emails": {"$sum": "$emails_found"},
                    "total_sessions": {"$count": {}}
                }}
            ]
            results = list(self.db.user_activity.aggregate(pipeline))
            if results:
                total_emails = results[0]["total_emails"]
                return {
                    "total_emails": total_emails,
                    "total_sessions": results[0]["total_sessions"],
                    "bill_pkr": total_emails * 0.5
                }
        except Exception as e:
            print(f"Error fetching user stats: {e}")
            
        return {"total_emails": 0, "total_sessions": 0, "bill_pkr": 0.0}

    def get_admin_dashboard_stats(self):
        """Get global stats for all users with bill calculations."""
        if not self._connected and not self.connect():
            return []
            
        try:
            pipeline = [
                {"$group": {
                    "_id": "$computer_name",
                    "total_emails": {"$sum": "$emails_found"},
                    "total_sessions": {"$count": {}},
                    "last_active": {"$max": "$last_updated"}
                }},
                {"$addFields": {
                    "bill_pkr": {"$multiply": ["$total_emails", 0.5]}
                }},
                {"$sort": {"total_emails": -1}}
            ]
            return list(self.db.user_activity.aggregate(pipeline))
        except Exception as e:
            print(f"Error fetching admin stats: {e}")
            return []

    def check_block_status(self):
        """Check if the current computer is blocked."""
        if not self._connected and not self.connect():
            return False
            
        try:
            user = self.db.users.find_one({"computer_name": self.computer_name})
            if user and user.get("is_blocked"):
                return True
        except Exception as e:
            print(f"Error checking block status: {e}")
        return False

    def toggle_block_status(self, target_computer: str, block: bool):
        """Admin function to block/unblock a computer."""
        if not self._connected and not self.connect():
            return False
            
        try:
            self.db.users.update_one(
                {"computer_name": target_computer},
                {"$set": {"is_blocked": block}},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"Error toggling block: {e}")
            return False

# Singleton instance for easy access across the app
db_manager = MongoDBManager()
