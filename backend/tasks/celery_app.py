# backend/tasks/celery_app.py
"""
Quantoryx — Celery Asynchronous Task Application Configuration.

Initializes Celery with Redis as both the message broker and task result backend.
Sets serialization parameters, concurrency behaviors, and registers task discovery paths [2].
"""

import os
import sys
from celery import Celery

# Guarantee the project root is in the search path for worker execution context
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load configuration endpoints from environment defaults
REDIS_BROKER_URL = os.environ.get("QUANTORYX_REDIS_BROKER_URL", "redis://localhost:6379/0")
REDIS_BACKEND_URL = os.environ.get("QUANTORYX_REDIS_BACKEND_URL", "redis://localhost:6379/1")

# Instantiate Celery Application
celery_app = Celery(
    "quantoryx_tasks",
    broker=REDIS_BROKER_URL,
    backend=REDIS_BACKEND_URL
)

# Configure advanced Celery execution parameters
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    
    # Task execution limits
    task_time_limit=3600,             # Max 1 hour before hard timeout
    task_soft_time_limit=3000,        # Graceful warning threshold at 50 minutes
    
    # Worker concurrency behavior
    worker_concurrency=int(os.environ.get("QUANTORYX_WORKER_CONCURRENCY", "4")),
    worker_prefetch_multiplier=1,      # Process 1 task at a time per channel (prevents bottleneck pooling)
    
    # Task result lifespan
    result_expires=86400,             # Cleanup execution task results after 24 hours
)

# Explicitly register tasks module paths for worker discovery
celery_app.autodiscover_tasks(["backend.tasks"])

# Expose broker parameters in worker consoles
if __name__ == "__main__":
    print(f"[+] Launching local Celery worker configuration interface...")
    print(f"    - Broker URL:  {REDIS_BROKER_URL}")
    print(f"    - Backend URL: {REDIS_BACKEND_URL}")
