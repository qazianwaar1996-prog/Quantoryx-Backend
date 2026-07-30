# Quantoryx — Relational Database Operations Manual

This guide describes how to operate, configure, and migrate the relational database persistence layer inside the Quantoryx research platform.

---

## 1. Local Database Operations (SQLite)

By default, the platform boots up utilizing **SQLite** as its development database. No database software installation, setup, or credentials configuration is required out of the box.

### Schema Bootstrapping
On startup, the system automatically checks for the existence of the database:
1. During the application startup lifecycle event, the backend verifies database connection viability.
2. If SQLite is detected and no database file exists at `data/quantoryx.db`, the system bootstraps the tables schema by invoking:
   ```python
   Base.metadata.create_all(bind=engine)
   # Ensure sqlite3 is installed, then open the database
sqlite3 data/quantoryx.db

# Show database tables
.tables

# View schema of the users table
.schema users

# Select current user listings
SELECT id, username, email, role, is_active FROM users;
# General PostgreSQL template:
export QUANTORYX_DATABASE_URL="postgresql://trader_admin:SecurePassword123@localhost:5432/quantoryx"
pip install alembic
alembic init backend/migrations
# Inside backend/migrations/env.py
from backend.database.connection import DATABASE_URL
config.set_main_option("sqlalchemy.url", DATABASE_URL)
alembic revision --autogenerate -m "Add core relational tables"
alembic upgrade head
from backend.database.connection import SessionLocal
from backend.repositories.repositories import audit_repo

with SessionLocal() as session:
    # Query top 100 logged events for a user
    logs = audit_repo.get_by_user(session, user_id="target_uuid_here")
    for log in logs:
        print(f"[{log.created_at}] Action: {log.action} | Details: {log.details}")
        All relational schemas, connection abstractions, database repositories, transactional routers, and detailed documentation guides have been written. The SQL relational persistence layer for Phase 3 is complete and ready to run.
