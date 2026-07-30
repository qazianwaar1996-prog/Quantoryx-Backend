# Quantoryx — Relational Database Architecture

This document describes the architectural patterns, database schemas, transactional scopes, and repository structures introduced in Phase 3 to establish a persistent relational database layer for the Quantoryx research framework.

---

## 1. Relational Schema Architecture

The relational schema is composed of 8 core tables mapped using SQLAlchemy's Declarative base. The User model acts as the primary parent node, propagating cascades, deletions, and operational histories.
┌──────────────────────────┐
                │          users           │
                └──────┬────────────┬──────┘
                       │ 1          │ 1
                       │            │
         1:1           │            │           1:N
    ┌──────────────────▼──┐     ┌───▼──────────────────┐
    │    user_settings    │     │      audit_logs      │
    └─────────────────────┘     └──────────────────────┘
                       │ 1
                       ├───────────────────┬───────────────────┐
                       │ 1:N               │ 1:N               │ 1:N
          ┌────────────▼─────┐┌────────────▼─────┐┌────────────▼─────┐
          │ saved_strategies ││  saved_backtests ││saved_optimizations
          └──────────────────┘└──────────────────┘└──────────────────┘
                       │ 1
                       ├───────────────────┐
                       │ 1:N               │ 1:N
          ┌────────────▼─────┐┌────────────▼─────┐
          │saved_ai_analyses ││  saved_reports   │
          └──────────────────┘└──────────────────┘
          ### Table Properties and Constraints

1. **`users`:** Core user identity table. Stores indexed UUID keys, unique usernames and emails, secure bcrypt-hashed passwords, role mappings, and operational status flags.
2. **`user_settings`:** One-to-one user preferences table. Links directly to `users.id` with a cascading delete constraint. Stores defaults (symbol, timeframe, leverage, spread) to decouple user metadata from system configuration settings.
3. **`saved_strategies`:** Parameter-persistence table. Stores named strategy configuration JSON records, allowing users to save and mark favorite parameter combinations.
4. **`saved_backtests`:** Historical backtesting results ledger. Stores strategy parameters as JSON, along with metrics (net profit, profit factor, drawdown, win rate, Sharpe ratio, and trade count).
5. **`saved_optimizations`:** Parameter sweep ledger. Stores best configurations, tested combination counts, and summaries of top-ranked parameter combinations.
6. **`saved_ai_analyses`:** Cognitive selections log. Keeps records of identified market regimes, selected strategies, confidence ratings, actions, and explanations.
7. **`saved_reports`:** CSV output database. Holds the filename, folder category, and storage size of reports compiled on disk.
8. **`audit_logs`:** Centralized system event tracker. Stores chronological events (logins, registrations, password modifications, token revocations, and system exceptions).

---

## 2. Session & Connection Management

The database session layer is configured inside `backend/database/connection.py` to balance the requirements of a lightweight development workspace with those of a high-concurrency production deployment.

### Context Management Patterns

#### 1. FastAPI Route Context (Dependency Injection)
Endpoints utilize FastAPI's dependency injection container (`Depends(get_db)`) to inject a scoped, transactional database session:
* The transaction is created at the beginning of the HTTP request.
* If an unhandled exception is raised during execution, a rollback is executed automatically.
* Once the response is written, the session is cleanly closed and returned to the pool.

#### 2. Standalone Context Manager (Backward-Compatible)
To avoid breaking Phase 2 service managers that do not utilize dependency injection, the `UserService` implements fallback connection scopes. If a method is called without a `db` session:
* The method automatically instantiates a scoped `SessionLocal()` using Python thread-safe connections.
* It performs operations, executes commits or rollbacks cleanly, and releases database resources before returning results.

### Connection Pooling Configurations
To support migration to production-level engines like PostgreSQL, the SQLAlchemy connection pool is configured with:
* `pool_pre_ping=True`: Actively pings the database connection before executing a transaction, silently recycling dead connections.
* `pool_recycle=3600`: Automatically recycles connection handlers older than 1 hour to prevent timeout drops by the SQL driver or firewall rules.

---

## 3. Repository Pattern

The repository pattern separates business logic from raw SQL operations, maintaining strict type safety and a clean API interface.
┌────────────────────────┐
   │     FastAPI Router     │
   └───────────┬────────────┘
               │ Employs Singleton
   ┌───────────▼────────────┐
   │     user_repo, ...     │ (backend/repositories/repositories.py)
   └───────────┬────────────┘
               │ Inherits CRUD
   ┌───────────▼────────────┐
   │     BaseRepository     │ (backend/repositories/base.py)
   └───────────┬────────────┘
               │ Query Executions
   ┌───────────▼────────────┐
   │   SQLAlchemy / Engine  │ (backend/database/connection.py)
   └────────────────────────┘
   * **`BaseRepository` (Generic Parent Class):** Exposes generic, reusable CRUD operations (`get`, `get_multi`, `create`, `update`, `remove`) parameterized over SQLAlchemy declarative classes.
* **Concrete Repositories (Specific Query Helpers):** Extends the base repository to implement targeted queries such as matching case-insensitive usernames (`ilike`), querying default profiles, and logging system audit trails.

---

## 4. Production Database Migration Roadmap

The architecture is fully modular, allowing SQLite (development) to be swapped out for a production database with minimal friction.

### Migration Variables
To point the application to a PostgreSQL database, set the environment variable:
```bash
export QUANTORYX_DATABASE_URL="postgresql://user:password@host:5432/database"
