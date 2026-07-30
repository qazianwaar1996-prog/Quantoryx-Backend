# backend/middleware/logging_middleware.py
"""
Quantoryx — Logging Middleware Module.

This module intercepts incoming REST API requests, records performance profile durations,
and captures runtime diagnostic issues using the system's centralized logger.
"""

import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from utils.logging_config import get_logger

# Initialize centralized logger
logger = get_logger("backend.middleware.logging")


class QuantoryxLoggingMiddleware(BaseHTTPMiddleware):
    """
    HTTP middleware implementing request profiling, path tracing,
    and unified response status logging.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Processes and profiles each incoming API request chronologically.
        """
        start_time = time.perf_counter()
        
        # Pull request elements for metadata indexing
        method = request.method
        path = request.url.path
        client_host = request.client.host if request.client else "Unknown"

        logger.info("--> Incoming Request: %s %s | Source: %s", method, path, client_host)

        try:
            # Propagate the request down the chain
            response = await call_next(request)
            
            # Profile duration
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            status_code = response.status_code

            # Determine appropriate log level depending on status code
            if status_code >= 500:
                logger.error(
                    "<-- Request Failed: %s %s | Status: %s | Duration: %s ms",
                    method, path, status_code, duration_ms
                )
            elif status_code >= 400:
                logger.warning(
                    "<-- Request Client Error: %s %s | Status: %s | Duration: %s ms",
                    method, path, status_code, duration_ms
                )
            else:
                logger.info(
                    "<-- Request Success: %s %s | Status: %s | Duration: %s ms",
                    method, path, status_code, duration_ms
                )

            # Inject the process duration header for client performance tracking
            response.headers["X-Process-Time-Ms"] = str(duration_ms)
            return response

        except Exception as e:
            # Handle unhandled pipeline or routing crashes safely
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            logger.critical(
                "<-- Request Crashed: %s %s | Error: %s | Duration: %s ms",
                method, path, str(e), duration_ms, exc_info=True
            )
            # Raise the exception up for global FastAPI handler treatment
            raise e
