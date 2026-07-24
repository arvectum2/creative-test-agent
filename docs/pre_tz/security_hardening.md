# CTA-PRE-011 — Local Security Hardening

Status: implemented.

The application is designed for NDA-restricted local processing on an analyst laptop or agency workstation. Security hardening is therefore fail-closed around network exposure, source-file integrity, browser sessions and report downloads.

## Local-only posture

At startup the application evaluates:

- bind host and public base URL;
- trusted hosts and CORS origins;
- cloud-LLM access;
- authentication secret quality when auth is enabled;
- password-length configuration when authentication is active;
- database locality;
- storage, export and backup directory writability;
- symbolic-link and world-writable directory warnings.

Blocking posture failures stop startup by default. The startup policy can be disabled only through `CTA_SECURITY_FAIL_CLOSED=false` for controlled diagnosis. Invalid boolean values do not silently disable fail-closed behaviour; they fall back to the secure default.

`/security/posture` exposes the non-secret check results to admin and manager roles. `/health` exposes only the aggregate posture status.

## Network and browser controls

- local-only mode rejects non-loopback Host headers and non-loopback peer addresses;
- Starlette trusted-host validation is enabled;
- CORS remains disabled unless explicit origins are configured;
- authenticated browser writes with an Origin header must match the configured public base URL or an explicit CORS origin exactly;
- declared and streamed request bodies are bounded by `CTA_SECURITY_MAX_REQUEST_SIZE_MB` (default: the larger of 260 MB or import limit + 10 MB);
- an oversized body is rejected with HTTP `413` before application processing completes.

## Response headers

Responses receive:

- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY`;
- `Referrer-Policy: no-referrer`;
- same-origin opener/resource policies;
- restrictive permissions policy;
- a self-only Content Security Policy;
- HSTS on HTTPS;
- `no-store` and `no-cache` for every non-static response.

## Authentication

The JSON API and HTML login form use the same controls:

- invalid logins return a generic error without revealing whether the account exists, is inactive or lacks a password;
- failed attempts are rate-limited both per client address and per client-address/email pair;
- the default is five failed attempts per five minutes;
- successful login clears the relevant failure windows;
- session cookies are HttpOnly, SameSite=Strict by default, path-scoped to `/`, and Secure when HTTPS or `CTA_SESSION_COOKIE_SECURE=true` is used;
- API and HTML logout delete the cookie with the same attributes;
- login, logout and other non-static responses are not cacheable.

The limiter is process-local and intentionally suitable for the five-to-six-user local workstation deployment. A later multi-process or distributed deployment must replace it with a shared store.

## File and report downloads

- client-provided attachment names are sanitized before use in `Content-Disposition`;
- immutable source downloads retain storage checksum verification;
- generated XLSX paths are confined to the configured storage root before any file access or checksum calculation;
- generated report bytes are verified against the persisted SHA-256 before download;
- sensitive downloads are never cacheable.

## Continuous verification

The mandatory CI workflow:

- runs with `contents: read` only;
- compiles the source tree;
- verifies the SQLAlchemy model registry and Alembic migrations;
- executes the local security-posture check;
- runs the complete regression test suite, including HTML/API auth, exact-origin, peer-address, streamed-body and report-path tests;
- uploads diagnostics on failure without committing or pushing files back to the pull-request branch;
- retains the closed-loop and demo-readiness checks.

## Environment controls

```text
CTA_SECURITY_FAIL_CLOSED=true
CTA_SECURITY_HEADERS_ENABLED=true
CTA_SECURITY_MAX_REQUEST_SIZE_MB=260
CTA_LOGIN_RATE_LIMIT_ATTEMPTS=5
CTA_LOGIN_RATE_LIMIT_WINDOW_SECONDS=300
CTA_SESSION_COOKIE_SECURE=false
CTA_SESSION_COOKIE_SAMESITE=strict
```

These controls are included in `.env.example`.

## Operational boundary

The security posture report is not a penetration test or formal compliance certification. Production deployment still requires operating-system encryption, restricted user accounts, encrypted backups, patch management and an approved incident/retention process.