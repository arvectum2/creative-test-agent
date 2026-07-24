# CTA-PRE-011 acceptance checklist

- Local-only mode rejects non-loopback hosts, peer addresses and non-local trusted hosts/CORS origins.
- Startup security posture is fail-closed for blocking misconfiguration, including invalid attempts to disable the guard accidentally.
- Cloud LLM use is a blocking failure in local-only mode.
- Authentication requires a strong secret when enabled.
- Browser writes enforce exact configured Origin restrictions when authentication is enabled.
- API and HTML login failures are generic and share client-wide plus client/email rate limits.
- Session cookies are HttpOnly, SameSite-controlled and Secure on HTTPS; API and HTML logout mirror deletion attributes.
- Security, privacy and anti-framing headers are applied globally.
- Every non-static response uses no-store/no-cache handling.
- Declared and streamed request bodies are bounded and oversized bodies return HTTP 413.
- Source/report attachment names are sanitized.
- Report paths are confined to storage root before file access and report downloads are SHA-256 verified.
- Security posture is available only to admin/manager roles when authentication is enabled.
- Mandatory CI uses read-only repository permissions and never commits diagnostics into the PR branch.
- Documentation and executable regression tests cover the controls.
- The result is operational hardening, not a penetration test or formal compliance certification.