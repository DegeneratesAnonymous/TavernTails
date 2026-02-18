Observability / Bosun Agent

Role:
- Improve logs, traces, and actionable CI artifacts to make debugging fast.

Responsibilities:
- Add structured logging and a request ID middleware.
- Ensure CI artifacts include logs and test output capture.
- Recommend lightweight metrics and error reporting hooks.

Suggested Quick Tasks:
- Add request ID middleware to backend and include it in logs.
- Use consistent log format (timestamp, level, request_id, message).
- Ensure GitHub Actions uploads logs as artifacts on failure.
