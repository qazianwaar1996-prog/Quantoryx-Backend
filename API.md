# Quantoryx — REST API Documentation Reference

The **Quantoryx REST API** provides programmatic access to the underlying quantitative research, simulation, and analysis engine. This API is self-contained and operates entirely on local datasets.

## Interactive Documentation Interfaces
Once the server is running, the interactive documentation interfaces can be accessed at the following local endpoints:
* **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **ReDoc UI:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## Endpoint Index

### User Identity & Access Control (Public / Rate-Limited)
* [`POST /api/auth/register`](#post-apiauthregister) — Register a new platform user profile.
* [`POST /api/auth/login`](#post-apiauthlogin) — Authenticate login credentials and obtain access tokens.
* [`POST /api/auth/refresh`](#post-apiauthrefresh) — Exchange expired access credentials using refresh tokens.
* [`POST /api/auth/logout`](#post-apiauthlogout) — Terminate user session and revoke refresh tokens.
* [`GET /api/auth/me`](#get-apiauthme) — Fetch the authenticated active user profile.
* [`PUT /api/auth/profile`](#put-apiauthprofile) — Update metadata elements on the current profile.
* [`POST /api/auth/change-password`](#post-apiauthchange-password) — Modify password credentials.

### System Diagnostics (Public)
* [`GET /api/health`](#get-apihealth) — Retrieve service operational uptime and timestamp parameters.
* [`GET /api/version`](#get-apiversion) — Retrieve framework metadata version indicators.
* [`GET /api/status`](#get-apistatus) — Retrieve system constants and active environment statuses.

### Simulation & Analysis (Auth Required)
* [`POST /api/backtest`](#post-apibacktest) — Simulate a single-strategy backtest run.
* [`POST /api/optimize`](#post-apioptimize) — Run parameter optimization sweeps on price histories.
* [`POST /api/walk-forward`](#post-apiwalk-forward) — Run rolling walk-forward validation slices.
* [`POST /api/paper-trading`](#post-apipaper-trading) — Run step-by-step account leverage/spread simulators.
* [`POST /api/ai-analysis`](#post-apiai-analysis) — Nominate a champion model using cognitive AI selections.

### Analytics & Reports (Auth Required)
* [`GET /api/dashboard`](#get-apidashboard) — Retrieve aggregated session overview metrics.
* [`GET /api/portfolio`](#get-apiportfolio) — Retrieve cash history and drawdown equity curves.
* [`GET /api/reports`](#get-apireports) — Index output files and document locations.
* [`GET /api/strategies`](#get-apistrategies) — Inspect registered strategy parameter profiles.
* [`GET /api/market-regime`](#get-apimarket-regime) — Inspect historical market regime distribution densities.

### System Control (Admin Clearance Required)
* [`GET /api/system-health`](#get-apisystem-health) — Run comprehensive code, validation, and directory health audits.

---

## User Identity & Access Control

### POST `/api/auth/register`
Creates a new user profile on the platform. Username and email must be unique. Subject to sliding-window rate limits.

* **Request Body:**
  ```json
  {
    "username": "trader1",
    "email": "trader1@quantoryx.com",
    "password": "SecurePassword123",
    "full_name": "Senior Quant Trader",
    "role": "user"
  }
