import socket
from datetime import datetime
from time import monotonic
from typing import Any

from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ConnectionFailure, OperationFailure, PyMongoError

# MongoDB connection details
MONGO_URI = "mongodb+srv://dbmatloob:222007matloob@cluster0.trwuj2z.mongodb.net/?appName=Cluster0"
DB_NAME = "matloob_scraper"
ACCESS_PENDING = "pending"
ACCESS_APPROVED = "approved"
ACCESS_BLOCKED = "blocked"
ACCESS_STATUSES = {ACCESS_PENDING, ACCESS_APPROVED, ACCESS_BLOCKED}
BILLING_RATE_PKR = 0.5


class MongoDBManager:
    """Manages tracking user activity and scraped lead counts in MongoDB."""

    def __init__(self):
        self.client = None
        self.db = None
        self.computer_name = socket.gethostname()
        self._connected = False
        self._last_failed_connect_at = 0.0
        self._connect_retry_seconds = 30.0

    def connect(self):
        """Establish connection to MongoDB."""
        if self._connected:
            return True

        now = monotonic()
        if now - self._last_failed_connect_at < self._connect_retry_seconds:
            return False

        try:
            self.client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=2000,
                connectTimeoutMS=2000,
            )
            # Simple check to verify connection
            self.client.admin.command("ismaster")
            self.db = self.client[DB_NAME]
            self._connected = True
            return True
        except (ConfigurationError, ConnectionFailure, OperationFailure, PyMongoError) as e:
            print(f"MongoDB Connection Error: {e}")
            self._connected = False
            self.db = None
            self.client = None
            self._last_failed_connect_at = now
            return False

    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self._connected = False

    def normalize_license_key(self, license_key: str) -> str:
        """Normalize a user-entered license key for stable DB lookups."""
        return str(license_key or "").strip().upper()

    def _user_filter(self, license_key: str, computer_name: str | None = None):
        """Build the identity filter shared by access and billing lookups."""
        return {
            "computer_name": computer_name or self.computer_name,
            "license_key": self.normalize_license_key(license_key),
        }

    def _connect_or_status(self):
        """Return False when MongoDB is not available for an access decision."""
        return self._connected or self.connect()

    def request_access(self, license_key: str, source: str = "", url: str = ""):
        """Create/update an access request and return whether scraping may start."""
        clean_license = self.normalize_license_key(license_key)
        now = datetime.now()
        if not clean_license:
            return {
                "allowed": False,
                "status": "license_required",
                "message": "License key is required before scraping can start.",
            }
        if not self._connect_or_status() or self.db is None:
            return {
                "allowed": False,
                "status": "db_unreachable",
                "message": "Access could not be verified because MongoDB is not reachable.",
            }

        identity = self._user_filter(clean_license)
        try:
            user = self.db.users.find_one(identity)
            if not user:
                self.db.users.update_one(
                    identity,
                    {
                        "$setOnInsert": {
                            **identity,
                            "access_status": ACCESS_PENDING,
                            "is_blocked": False,
                            "first_seen": now,
                        },
                        "$set": {
                            "last_seen": now,
                            "last_request_at": now,
                            "last_requested_source": source,
                            "last_requested_url": url,
                            "updated_at": now,
                        },
                    },
                    upsert=True,
                )
                return {
                    "allowed": False,
                    "status": ACCESS_PENDING,
                    "message": (
                        "Access request sent to admin. Please wait for approval before scraping."
                    ),
                }

            status = str(user.get("access_status") or "").strip().lower()
            if user.get("is_blocked"):
                status = ACCESS_BLOCKED
            if not status:
                status = ACCESS_APPROVED if not user.get("is_blocked") else ACCESS_BLOCKED

            self.db.users.update_one(
                identity,
                {
                    "$set": {
                        "access_status": status,
                        "last_seen": now,
                        "last_request_at": now,
                        "last_requested_source": source,
                        "last_requested_url": url,
                        "updated_at": now,
                    }
                },
            )

            if status == ACCESS_APPROVED:
                return {
                    "allowed": True,
                    "status": ACCESS_APPROVED,
                    "message": "Access approved.",
                }
            if status == ACCESS_BLOCKED:
                return {
                    "allowed": False,
                    "status": ACCESS_BLOCKED,
                    "message": "Access blocked by admin. Please clear dues to resume.",
                }
            return {
                "allowed": False,
                "status": ACCESS_PENDING,
                "message": "Access pending. Admin approval is required before scraping.",
            }
        except Exception as e:
            print(f"Error requesting access in MongoDB: {e}")
            return {
                "allowed": False,
                "status": "db_error",
                "message": "Access check failed. Please try again after DB is reachable.",
            }

    def track_start(self, source: str, url: str, license_key: str = ""):
        """Record the start of a scraping session."""
        if not self._connected and not self.connect():
            return None
        if self.db is None:
            return None

        clean_license = self.normalize_license_key(license_key)
        activity = {
            "computer_name": self.computer_name,
            "license_key": clean_license,
            "source": source,
            "target_url": url,
            "start_time": datetime.now(),
            "status": "running",
            "emails_found": 0,
            "last_updated": datetime.now(),
        }

        try:
            result = self.db.user_activity.insert_one(activity)
            return result.inserted_id
        except Exception as e:
            print(f"Error tracking start in MongoDB: {e}")
            return None

    def update_activity(self, activity_id: Any, emails_count: int, status: str = "running"):
        """Update the email count for an active session."""
        if not self._connected or activity_id is None or self.db is None:
            return

        try:
            self.db.user_activity.update_one(
                {"_id": activity_id},
                {
                    "$set": {
                        "emails_found": emails_count,
                        "status": status,
                        "last_updated": datetime.now(),
                    }
                },
            )
        except Exception as e:
            print(f"Error updating MongoDB activity: {e}")

    def get_user_stats(self, license_key: str = ""):
        """Get stats for the current computer, including bill."""
        if not self._connected and not self.connect():
            return {"total_emails": 0, "total_sessions": 0, "bill_pkr": 0.0}
        if self.db is None:
            return {"total_emails": 0, "total_sessions": 0, "bill_pkr": 0.0}

        clean_license = self.normalize_license_key(license_key)
        match_filter = {"computer_name": self.computer_name}
        if clean_license:
            match_filter["license_key"] = clean_license

        try:
            pipeline = [
                {"$match": match_filter},
                {
                    "$group": {
                        "_id": {"computer_name": "$computer_name", "license_key": "$license_key"},
                        "total_emails": {"$sum": "$emails_found"},
                        "total_sessions": {"$count": {}},
                    }
                },
            ]
            results = list(self.db.user_activity.aggregate(pipeline))
            if results:
                total_emails = results[0]["total_emails"]
                return {
                    "total_emails": total_emails,
                    "total_sessions": results[0]["total_sessions"],
                    "bill_pkr": total_emails * BILLING_RATE_PKR,
                }
        except Exception as e:
            print(f"Error fetching user stats: {e}")

        return {"total_emails": 0, "total_sessions": 0, "bill_pkr": 0.0}

    def get_admin_dashboard_stats(self):
        """Get global stats for all users with bill calculations."""
        if not self._connected and not self.connect():
            return []
        if self.db is None:
            return []

        try:
            pipeline = [
                {
                    "$group": {
                        "_id": {
                            "computer_name": "$computer_name",
                            "license_key": "$license_key",
                        },
                        "total_emails": {"$sum": "$emails_found"},
                        "total_sessions": {"$count": {}},
                        "last_active": {"$max": "$last_updated"},
                    }
                },
                {
                    "$addFields": {
                        "computer_name": "$_id.computer_name",
                        "license_key": {"$ifNull": ["$_id.license_key", ""]},
                        "bill_pkr": {"$multiply": ["$total_emails", BILLING_RATE_PKR]},
                    }
                },
                {"$sort": {"total_emails": -1}},
            ]
            activity_rows = list(self.db.user_activity.aggregate(pipeline))
            users = self.get_registered_users()
            users_by_key = {
                (user.get("computer_name", ""), user.get("license_key", "")): user for user in users
            }
            seen_keys = set()
            rows = []

            for row in activity_rows:
                computer_name = row.get("computer_name") or "Unknown"
                license_key = row.get("license_key") or ""
                key = (computer_name, license_key)
                user = users_by_key.get(key, {})
                access_status = self._coerce_access_status(user)
                normalized_row = {
                    "_id": computer_name,
                    "computer_name": computer_name,
                    "license_key": license_key,
                    "access_status": access_status,
                    "is_blocked": access_status == ACCESS_BLOCKED,
                    "total_emails": row.get("total_emails", 0),
                    "total_sessions": row.get("total_sessions", 0),
                    "last_active": row.get("last_active"),
                    "bill_pkr": row.get("bill_pkr", 0.0),
                    "last_request_at": user.get("last_request_at"),
                    "last_requested_source": user.get("last_requested_source", ""),
                    "last_requested_url": user.get("last_requested_url", ""),
                }
                rows.append(normalized_row)
                seen_keys.add(key)

            for user in users:
                computer_name = user.get("computer_name") or "Unknown"
                license_key = user.get("license_key") or ""
                key = (computer_name, license_key)
                if key in seen_keys:
                    continue
                rows.append(
                    {
                        "_id": computer_name,
                        "computer_name": computer_name,
                        "license_key": license_key,
                        "access_status": self._coerce_access_status(user),
                        "is_blocked": self._coerce_access_status(user) == ACCESS_BLOCKED,
                        "total_emails": 0,
                        "total_sessions": 0,
                        "last_active": None,
                        "bill_pkr": 0.0,
                        "last_request_at": user.get("last_request_at"),
                        "last_requested_source": user.get("last_requested_source", ""),
                        "last_requested_url": user.get("last_requested_url", ""),
                    }
                )

            rows.sort(
                key=lambda row: (
                    0 if row.get("access_status") == ACCESS_PENDING else 1,
                    -int(row.get("total_emails") or 0),
                    str(row.get("computer_name") or ""),
                )
            )
            return rows
        except Exception as e:
            print(f"Error fetching admin stats: {e}")
            return []

    def _coerce_access_status(self, user):
        """Map legacy/current user records to one access status."""
        status = str(user.get("access_status") or "").strip().lower()
        if user.get("is_blocked"):
            return ACCESS_BLOCKED
        if status in ACCESS_STATUSES:
            return status
        return ACCESS_PENDING

    def get_registered_users(self):
        """Return all known user access records."""
        if not self._connected and not self.connect():
            return []
        if self.db is None:
            return []

        try:
            return list(self.db.users.find({}))
        except Exception as e:
            print(f"Error fetching registered users: {e}")
            return []

    def check_block_status(self, license_key: str = ""):
        """Check if the current computer is blocked."""
        if not self._connected and not self.connect():
            return False
        if self.db is None:
            return False

        try:
            clean_license = self.normalize_license_key(license_key)
            user_filter = {"computer_name": self.computer_name}
            if clean_license:
                user_filter["license_key"] = clean_license
            user = self.db.users.find_one(user_filter)
            return bool(user and self._coerce_access_status(user) == ACCESS_BLOCKED)
        except Exception as e:
            print(f"Error checking block status: {e}")
        return False

    def set_user_access_status(self, target_computer: str, license_key: str, status: str):
        """Admin function to approve, block, or return a user to pending."""
        if not self._connected and not self.connect():
            return False
        if self.db is None:
            return False

        clean_computer = str(target_computer or "").strip()
        clean_license = self.normalize_license_key(license_key)
        clean_status = str(status or "").strip().lower()
        if not clean_computer or not clean_license or clean_status not in ACCESS_STATUSES:
            return False

        is_blocked = clean_status == ACCESS_BLOCKED
        now = datetime.now()
        set_fields = {
            "computer_name": clean_computer,
            "license_key": clean_license,
            "access_status": clean_status,
            "is_blocked": is_blocked,
            "updated_at": now,
        }
        if clean_status == ACCESS_APPROVED:
            set_fields["approved_at"] = now
        elif clean_status == ACCESS_BLOCKED:
            set_fields["blocked_at"] = now

        try:
            self.db.users.update_one(
                {"computer_name": clean_computer, "license_key": clean_license},
                {"$set": set_fields, "$setOnInsert": {"first_seen": now}},
                upsert=True,
            )
            return True
        except Exception as e:
            print(f"Error setting access status: {e}")
            return False

    def toggle_block_status(self, target_computer: str, block: bool, license_key: str = ""):
        """Admin function to block/unblock a computer."""
        status = ACCESS_BLOCKED if block else ACCESS_APPROVED
        return self.set_user_access_status(target_computer, license_key, status)


# Singleton instance for easy access across the app
db_manager = MongoDBManager()
