### Module Responsibilities

1. **`backend/main.py` (The Entry Point):**
   * Configures FastAPI application metadata.
   * Maps CORS global policy domains.
   * Injects the processing logging middleware.
   * Configures global exception handlers to capture ValueError blocks as HTTP 400 structures and system crashes as HTTP 500 structures.

2. **`backend/middleware/logging_middleware.py` (Operational Telemetry):**
   * Intercepts, profiles, and tracks processing durations of incoming HTTP requests.
   * Formulates structured messages directed to the system's centralized console log stream.
   * Injects custom `X-Process-Time-Ms` response header trackers.

3. **`backend/schemas/api_schemas.py` (Structural Validation):**
   * Maps, validates, and serializes all JSON payloads using Pydantic models.
   * Defines the 14 structural response data contracts ensuring API type safety.

4. **`backend/api/endpoints.py` (HTTP Routers):**
   * Declares REST endpoints, routing mappings, response classes, and error codes.
   * Binds custom query parameters and translates ValueError codes cleanly.

5. **`backend/services/quantoryx_service.py` (Unified Service Layer):**
   * Adapts FastAPI requests to the underlying Quantoryx code.
   * Handles defensive file loading and automatic synthetic data generation fallback logic.
   * Standardizes response dictionaries to align with Pydantic serialization properties.

---

## 3. Core Data & Request Flows

### POST /backtest Execution Flow
The following sequence details how the system evaluates parameters:

1. **Client Request:** Post payload JSON structure (`BacktestRequest`) containing strategy, symbol, timeframe, and parameters.
2. **Structural Validation:** Pydantic models check types and assign appropriate default parameter rules.
3. **Dataset Verification:** `QuantoryxService` locates the instrument history file via `PathManager`. If absent, a realistic synthetic pricing set is compiled instantly inside `data/` to keep operations flowing.
4. **Indicator and Signal Generation:** `BacktestEngine` loads the registry class, normalizes column casings, tags regimes, and simulates trade positions step-by-step.
5. **Report Logging:** Execution results are persisted to `reports/` and `logs/` folders as requested.
6. **KPI Mapping:** Metric structures are calculated and serialized as a `BacktestResponse` model.

---

## 4. Diagnostics & System Telemetry

The backend integrates deeply with the framework's diagnostic components:

* **FastAPI Lifecycles:** On application startup, the system validates that output directories are mapped, workspace environments are configured, and historical pricing directories exist.
* **GET /system-health:** This endpoint triggers `PipelineValidator` dynamically. It validates Python imports, checks code quality, scans for duplicate structures using AST syntax tree parsing, and checks reports schemas, outputting a real-time system audit.
* **Request Profiling:** The middleware measures latency on every request with sub-millisecond precision, allowing operators to diagnose performance bottlenecks or memory spikes immediately in local consoles.
