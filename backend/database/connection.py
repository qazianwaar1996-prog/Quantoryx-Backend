# backend/database/connection.py
"""
Quantoryx — Database Connection & Session Management Module.

This module initializes the SQLAlchemy engine, configures session pools,
supports seamless migration between SQLite (development) and PostgreSQL (production),
and implements automatic startup checks and database health audits.
"""

import os
import sys
from typing import Generator, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure root is in path for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.logging_config import get_logger
from utils.path_manager import PathManager

logger = get_logger("backend.database.connection")

# =====================================================================
# CONFIGURATION & DATABASE URL RESOLUTION
# =====================================================================
# Default to SQLite database located in the standardized data/ folder
PathManager.initialize_workspace()
sqlite_db_path = os.path.join(PathManager.DIRECTORIES["data"], "quantoryx.db")
default_db_url = f"sqlite:///{sqlite_db_path}"

# Load connection string from environment
# Railway injects DATABASE_URL for Postgres addons; also accept QUANTORYX_DATABASE_URL
# for explicit overrides. Fall back to local SQLite for development.
DATABASE_URL = (
    os.environ.get("QUANTORYX_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or default_db_url
)

# Adjust standard PostgreSQL driver schemes if required
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Establish connection arguments and pool config based on database type.
# SQLite: requires check_same_thread=False for multi-threaded FastAPI use.
#         Uses StaticPool so all threads share one connection (avoids
#         "SQLite objects created in a thread can only be used in that thread").
#         pool_recycle is NOT supported by SQLite and must be omitted.
# PostgreSQL: standard pool with pre-ping and 1-hour recycle.
connect_args = {}
engine_kwargs = {"pool_pre_ping": True}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine_kwargs["connect_args"] = connect_args
    engine_kwargs["poolclass"] = StaticPool
else:
    engine_kwargs["connect_args"] = connect_args
    engine_kwargs["pool_recycle"] = 3600

# Initialize SQLAlchemy Engine
try:
    engine = create_engine(DATABASE_URL, **engine_kwargs)
    logger.info("SQLAlchemy database engine initialized on URL: %s", DATABASE_URL.split("@")[-1])  # Exclude user:pass from logs
except Exception as e:
    logger.critical("Failed to create database engine: %s", str(e), exc_info=True)
    raise e

# Create Thread-local Session Factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for declarative ORM models
Base = declarative_base()


# =====================================================================
# SESSION MANAGEMENT & HEALTH CHECKS
# =====================================================================

def get_db() -> Generator:
    """
    FastAPI dependency that yields a scoped database transaction session,
    guaranteeing automatic rollback on failure and transaction closure on completion.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error("Transaction exception triggered. Rollback executed: %s", str(e))
        raise e
    finally:
        db.close()


def check_db_health() -> Tuple[bool, str]:
    """
    Performs a live database health check using a lightweight query.
    Returns:
        Tuple of (is_healthy, status_message)
    """
    try:
        # Create an isolated connection to perform ping test
        with engine.connect() as conn:
            # Query standard across SQLite and PostgreSQL
            conn.execute(text("SELECT 1"))
        return True, "Database connection is healthy and responsive."
    except Exception as e:
        error_msg = f"Database health audit failed: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def initialize_database() -> bool:
    """
    Performs automatic startup checks. Creates database tables if using SQLite,
    and runs lightweight migration readiness checks.
    """
    logger.info("Running automatic database startup checks...")
    healthy, msg = check_db_health()
    if not healthy:
        logger.critical("Startup check failed: Database is unresponsive. %s", msg)
        return False

    try:
        # For SQLite development runs, automatically bootstrap the tables on launch
        # In a fully migrated production setup, migrations are handled via Alembic
        if DATABASE_URL.startswith("sqlite"):
            logger.info("SQLite connection detected. Bootstrapping database schema tables automatically...")
            # Import models dynamically on demand to ensure they are registered with Base
            import backend.models.models  # noqa: F401
            Base.metadata.create_all(bind=engine)
            logger.info("Schema bootstrapped successfully.")
        else:
            logger.info("Production database detected. Alembic migration scheme is recommended for updates.")
        
        return True
    except Exception as e:
        logger.critical("Database initialization encountered an error: %s", str(e), exc_info=True)
        return False
