import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class PendingNotification:
    message: str
    created_at: str
    notification_type: str
    priority: int = 2
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PendingNotification':
        return cls(**data)


class PendingNotificationQueue:
    def __init__(self, storage_path: str = "pending_notifications.json"):
        self.storage_path = Path(storage_path)
        self._lock = Lock()
        self._ensure_storage_exists()
    
    def _ensure_storage_exists(self) -> None:
        if not self.storage_path.exists():
            self._write_queue([])
    
    def _read_queue(self) -> List[dict]:
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _write_queue(self, queue: List[dict]) -> None:
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)
    
    def add(self, notification: PendingNotification) -> None:
        with self._lock:
            queue = self._read_queue()
            queue.append(notification.to_dict())
            self._write_queue(queue)
            logger.info(f"Added pending notification: {notification.notification_type}")
    
    def get_all(self) -> List[PendingNotification]:
        with self._lock:
            queue = self._read_queue()
            return [PendingNotification.from_dict(item) for item in queue]
    
    def remove(self, index: int) -> None:
        with self._lock:
            queue = self._read_queue()
            if 0 <= index < len(queue):
                queue.pop(index)
                self._write_queue(queue)
    
    def clear(self) -> None:
        with self._lock:
            self._write_queue([])
            logger.info("Cleared all pending notifications")
    
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._read_queue()) == 0
    
    def count(self) -> int:
        with self._lock:
            return len(self._read_queue())


_queue_instance: Optional[PendingNotificationQueue] = None


def get_notification_queue(storage_path: str = "pending_notifications.json") -> PendingNotificationQueue:
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = PendingNotificationQueue(storage_path)
    return _queue_instance