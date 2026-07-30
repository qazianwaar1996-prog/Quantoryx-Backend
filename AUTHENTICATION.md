# Quantoryx — Authentication & Security Architecture

This document describes the design patterns, cryptographic configurations, and authorization flows implemented in Phase 2 of the Quantoryx algorithmic trading backend.

---

## 1. Security Architecture Overview

The system implements a local, stateless, and robust token-based authentication system based on the JSON Web Token (JWT) standard. Business routes are protected by robust dependencies, while sensitive endpoints utilize Role-Based Access Control (RBAC).
---

## 2. Cryptographic Specifications

### Password Hashing
* **Algorithm:** Blowfish-based salt derivation (via the `bcrypt` module).
* **Work Factor (Rounds):** 12 (strikes a secure balance between computational security and backend request latency).
* **Encoding:** Plain-text passwords are UTF-8 encoded before hashing. Hashes are decoded back to string format for storage.

### Token Signing
* **Signature Algorithm:** HMAC-SHA256 (`HS256`).
* **Secret Key:** Read from the `QUANTORYX_SECRET_KEY` environment variable. If missing, the backend generates a secure 64-character hexadecimal ephemeral key on startup (and warns the administrator).
* **Access Token Expiration:** 30 Minutes.
* **Refresh Token Expiration:** 7 Days.

---

## 3. Storage & Token Rotation (Stateless and Revocable)

### Lightweight Persistence (`data/users.json`)
The user persistence layer is a modular JSON-based storage file managed atomically via Python thread locks. It stores:
* User identifiers and metadata (username, email, registration times).
* Role-based credentials (`user` or `admin`).
* Secure bcrypt-hashed password values.
* **`revoked_tokens`**: A list of refresh tokens blacklisted during logout or token rotation.

### Token Rotation Strategy
To prevent refresh token hijack or replay attacks:
1. When a client executes `/api/auth/refresh` to obtain a fresh access token, the system validates the token signature and checks if it has been marked as revoked.
2. Upon approval, the system generates a **new access token** and a **new refresh token**.
3. The old refresh token is added to the user's `revoked_tokens` array on disk, preventing it from being used again.
4. If a client attempts to reuse a revoked refresh token, the system rejects the request immediately.

---

## 4. Operational Telemetry & Protections

### Sliding-Window In-Memory Rate Limiter
To guard sensitive auth endpoints (specifically registration and login) against brute-force attacks, the backend implements a sliding-window rate limiter per client IP:
* **Monitoring Window:** 60 Seconds.
* **Maximum Requests:** 100 per IP address.
* **Action:** Exceeding this limit yields an `HTTP 429 Too Many Requests` status code and rejects processing.

### Custom HTTP Security Headers
To follow modern secure API deployment practices, custom middleware injects the following response headers on every request:
* `X-Frame-Options: DENY` (prevents clickjacking attacks).
* `X-Content-Type-Options: nosniff` (prevents MIME-type sniffing).
* `X-XSS-Protection: 1; mode=block` (mitigates cross-site scripting risks).
* `Strict-Transport-Security: max-age=31536000; includeSubDomains` (forces HTTPS usage).
* `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'` (enforces content safety).

---

## 5. User Roles and RBAC Rules

The backend defines two levels of user clearance:
1. **User Role (`user`):** Has standard privileges. Can run backtests, optimizations, walk-forward pipelines, paper-trading simulations, and fetch dashboard indicators.
2. **Admin Role (`admin`):** Has elevated clearance. In addition to user privileges, only administrators can access system performance profiling and code-scanning diagnostics (`GET /api/system-health`), preventing untrusted resource-intensive sweeps.
