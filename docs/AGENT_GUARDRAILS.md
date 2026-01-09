# Agent Guardrails and Security Checklist

_Last updated: 2026-01-09_

This document provides a beginner-friendly checklist of security guardrails and best practices for TavernTAIls AI agents. These safeguards protect users, prevent abuse, and ensure the system operates safely and reliably.

## Quick Start

If you're new to agent security, start here:

1. **Enable audit logging**: Set `TAVERNTAILS_ENABLE_AUDIT_LOGGING=true` in your `.env`
2. **Turn on content moderation**: Set `TAVERNTAILS_ENABLE_CONTENT_MODERATION=true`
3. **Use RBAC for hidden documents**: Ensure only hosts can access `visibility=hidden` documents
4. **Review the full checklist below** and implement items marked **[CRITICAL]** first
5. **Test with the security smoke test** (see Section 11)

**For production deployments**, all **[CRITICAL]** and **[HIGH]** priority items must be implemented.

---

## 1. Role-Based Access Control (RBAC) **[CRITICAL]**

### What it is
RBAC ensures users can only access resources appropriate to their role (`player`, `host`, `admin`).

### Implementation checklist
- [ ] Define roles in the database schema (`users.role` field)
- [ ] Implement role checks in all agent endpoints
- [ ] Use FastAPI dependencies to enforce role requirements
- [ ] Audit: Log all access attempts to sensitive resources

### Example
```python
from fastapi import Depends, HTTPException
from .auth import get_current_user

async def require_host(user = Depends(get_current_user)):
    if user.role not in ["host", "admin"]:
        raise HTTPException(403, "Host role required")
    return user

@router.post("/campaigns/{id}/hidden-docs")
async def create_hidden_doc(id: str, user = Depends(require_host)):
    # Only hosts can create hidden documents
    ...
```

### Testing
- Test that players cannot access hidden documents
- Test that non-hosts cannot modify campaign settings
- Test that admin role has appropriate elevated permissions

---

## 2. Allowlists and Denylists **[HIGH]**

### What it is
Restrict which external services, domains, and endpoints agents can interact with.

### Implementation checklist
- [ ] Maintain allowlist of approved LLM/image providers (OpenAI, Stability AI, etc.)
- [ ] Define egress network allowlist (which external domains are permitted)
- [ ] Block access to internal network ranges (RFC 1918 addresses)
- [ ] Validate all URLs before making external requests
- [ ] Reject any user-provided URLs that don't match allowlist

### Example allowlists
```python
# In settings.py or config
ALLOWED_LLM_PROVIDERS = [
    "api.openai.com",
    "api.stability.ai",
    "api.anthropic.com"
]

ALLOWED_IMAGE_DOMAINS = [
    "cdn.taverntails.com",
    "s3.amazonaws.com"  # Only if using S3
]

# RFC 1918 private ranges to block
BLOCKED_IP_RANGES = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8"
]
```

### Testing
- Test that requests to non-allowlisted domains are rejected
- Test that internal IP ranges cannot be accessed
- Test that user-provided URLs are validated

---

## 3. Scoped API Tokens **[CRITICAL]**

### What it is
Use minimal-privilege tokens for external services to limit damage if credentials are compromised.

### Implementation checklist
- [ ] Use separate API keys for dev, staging, and production
- [ ] Request minimal scopes from OAuth providers (e.g., DnD Beyond read-only)
- [ ] Store tokens in environment variables or secret manager (never in code)
- [ ] Rotate tokens regularly (see `docs/SECRET_MANAGEMENT.md`)
- [ ] Revoke tokens immediately if compromise is suspected

### Example
```bash
# .env - Use read-only scopes where possible
OPENAI_API_KEY=sk-...  # Scoped to text generation only
STABILITY_API_KEY=...  # Scoped to image generation only
DNDBEYOND_TOKEN=...    # Read-only character access
```

### Testing
- Verify tokens are never logged or returned in API responses
- Test that invalid/expired tokens are rejected
- Confirm tokens are not committed to git (check `.gitignore`)

---

## 4. Pydantic Schema Validation **[CRITICAL]**

### What it is
Use Pydantic models to validate all inputs and outputs, preventing injection attacks and malformed data.

### Implementation checklist
- [ ] Define Pydantic models for all agent inputs/outputs
- [ ] Use strict types (no `Any` unless necessary)
- [ ] Set reasonable length limits on string fields
- [ ] Validate enum values for constrained fields
- [ ] Sanitize/escape HTML content before rendering

### Example
```python
from pydantic import BaseModel, Field, validator

class NarrativeRequest(BaseModel):
    session_id: str = Field(..., max_length=64)
    context: str = Field(..., max_length=10000)
    style: str = Field(default="neutral", regex="^(neutral|dramatic|humorous)$")
    
    @validator('context')
    def sanitize_context(cls, v):
        # Remove potentially dangerous content
        return v.replace("<script>", "").replace("</script>", "")
```

### Testing
- Test with oversized inputs (should be rejected)
- Test with invalid enum values (should fail validation)
- Test with special characters and HTML (should be sanitized)

---

## 5. Content Moderation **[HIGH]**

### What it is
Filter AI-generated content to prevent offensive, harmful, or policy-violating output.

### Implementation checklist
- [ ] Enable content moderation API (OpenAI Moderation, Perspective API, etc.)
- [ ] Check all LLM outputs before displaying to users
- [ ] Log moderation failures to `agent_events` table
- [ ] Provide fallback responses when content is flagged
- [ ] Allow hosts to override moderation for mature campaigns (with warnings)

### Example
```python
async def moderate_content(text: str) -> bool:
    """Returns True if content passes moderation, False otherwise."""
    if not os.getenv("TAVERNTAILS_ENABLE_CONTENT_MODERATION") == "true":
        return True  # Skip in dev mode
    
    # Call moderation API
    response = await openai.Moderation.create(input=text)
    flagged = response["results"][0]["flagged"]
    
    if flagged:
        logger.warning(f"Content moderation flagged: {text[:100]}")
        # Log to agent_events for PM review
        
    return not flagged
```

### Testing
- Test with known policy-violating content (should be blocked)
- Test with borderline content (verify behavior matches policy)
- Test that moderation can be disabled for development

---

## 6. Rate Limits and Quotas **[HIGH]**

### What it is
Prevent abuse by limiting how many requests users can make within a time window.

### Implementation checklist
- [ ] Implement rate limiting middleware (see Section 10 for placeholder)
- [ ] Set per-user limits (e.g., 100 requests/hour per user)
- [ ] Set per-endpoint limits for expensive operations (e.g., 10 image generations/hour)
- [ ] Return 429 status code when limits exceeded
- [ ] Allow higher limits for trusted/premium users

### Example limits
```python
# Per-user global rate limit
RATE_LIMIT_REQUESTS_PER_HOUR = 100

# Per-endpoint limits for expensive operations
RATE_LIMITS = {
    "/narrative/generate": 30,    # 30 requests/hour
    "/image/generate": 10,         # 10 images/hour
    "/chat": 100,                  # 100 messages/hour
}
```

### Testing
- Test that users receive 429 after exceeding limits
- Test that limits reset after the time window
- Test that different endpoints have independent limits

---

## 7. Audit Logging **[CRITICAL]**

### What it is
Record all significant agent actions for security review, debugging, and compliance.

### Implementation checklist
- [ ] Log all agent API calls to `agent_events` table
- [ ] Include: timestamp, user, action, resource, result (success/failure)
- [ ] Log authentication events (login, logout, failed attempts)
- [ ] Log access to sensitive resources (hidden documents, admin functions)
- [ ] Store logs for at least 90 days
- [ ] Provide audit log search/filter UI for PM

### Required fields
```python
class AgentEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: Optional[str] = None
    agent: str          # e.g., "narrative", "image"
    action: str         # e.g., "generate", "access_hidden_doc"
    resource_id: Optional[str] = None    # Campaign/session/document ID
    result: str         # "success", "failure", "blocked"
    details: Optional[str] = None        # Additional context (JSON)
```

### Testing
- Verify all agent calls create audit log entries
- Test that logs include all required fields
- Confirm PM can query logs by user, date, action

---

## 8. Timeouts and Circuit Breakers **[MEDIUM]**

### What it is
Prevent cascading failures and resource exhaustion by limiting how long operations can run.

### Implementation checklist
- [ ] Set timeout for all agent operations (default: 30 seconds)
- [ ] Implement circuit breaker for external API calls (LLM, image generation)
- [ ] Return graceful error messages when timeouts occur
- [ ] Track timeout frequency and alert if it exceeds threshold
- [ ] Implement exponential backoff for retries

### Example
```python
import asyncio
from functools import wraps

def with_timeout(seconds: int = 30):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                logger.error(f"{func.__name__} timed out after {seconds}s")
                raise HTTPException(504, f"Operation timed out")
        return wrapper
    return decorator

@with_timeout(30)
async def generate_narrative(request: NarrativeRequest):
    # This will timeout after 30 seconds
    ...
```

### Testing
- Test that long-running operations timeout correctly
- Test that circuit breaker opens after consecutive failures
- Test that retry logic uses exponential backoff

---

## 9. Human-in-the-Loop for Risky Actions **[HIGH]**

### What it is
Require manual approval from a host or PM before executing high-impact actions.

### Implementation checklist
- [ ] Flag risky actions: publish narrative, delete campaign, change user roles
- [ ] Queue risky actions for host/PM review instead of executing immediately
- [ ] Provide approval UI for hosts to review and approve/reject
- [ ] Log all approvals and rejections to audit log
- [ ] Notify users when their action is pending approval

### Risky actions requiring approval
- Publishing agent-generated narrative (GM Orchestrator review)
- Modifying hidden documents
- Deleting campaigns with active sessions
- Changing user roles or permissions
- Bulk operations affecting multiple users/resources

### Example
```python
async def publish_narrative(narrative: str, session_id: str, user):
    # Queue for GM Orchestrator review
    pending = PendingAction(
        action="publish_narrative",
        resource_id=session_id,
        data=narrative,
        submitted_by=user.id,
        status="pending"
    )
    db.add(pending)
    await db.commit()
    
    # Notify host for review
    await notify_host(session_id, "Narrative pending review")
    
    return {"status": "pending", "message": "Awaiting host approval"}
```

### Testing
- Test that risky actions create pending approval records
- Test that actions execute only after approval
- Test that rejections are logged and users are notified

---

## 10. Egress Network Allowlists **[MEDIUM]**

### What it is
Control which external networks agents can communicate with to prevent data exfiltration.

### Implementation checklist
- [ ] Define allowlist of permitted external domains (see Section 2)
- [ ] Block access to cloud metadata endpoints (169.254.169.254)
- [ ] Block access to internal/private IP ranges
- [ ] Validate all URLs before making HTTP requests
- [ ] Log all outbound requests for review

### Blocked endpoints
```python
BLOCKED_ENDPOINTS = [
    "169.254.169.254",           # AWS/GCP metadata
    "metadata.google.internal",  # GCP metadata
    "localhost",
    "127.0.0.1",
]
```

### Testing
- Test that requests to metadata endpoints are blocked
- Test that requests to internal IPs are blocked
- Test that only allowlisted domains are accessible

---

## 11. Secrets Hygiene **[CRITICAL]**

### What it is
Ensure secrets (API keys, passwords, tokens) are never exposed in code, logs, or responses.

### Implementation checklist
- [ ] Store all secrets in environment variables or secret manager
- [ ] Add `.env` to `.gitignore` (verify it's already there)
- [ ] Never log full secrets (mask/truncate if logging is necessary)
- [ ] Never return secrets in API responses
- [ ] Scan code with `trufflehog` or similar tool before releases
- [ ] Rotate secrets regularly (see `docs/SECRET_MANAGEMENT.md`)

### Example
```python
# GOOD: Read from environment
api_key = os.getenv("OPENAI_API_KEY")

# BAD: Hardcoded secret
api_key = "sk-1234567890abcdef"  # NEVER DO THIS

# GOOD: Masked logging
logger.info(f"Using API key: {api_key[:8]}...")

# BAD: Full secret in logs
logger.info(f"Using API key: {api_key}")  # NEVER DO THIS
```

### Testing
- Run `git log -p | grep -i "api_key\|secret\|password"` to check history
- Use `trufflehog` to scan for leaked secrets
- Verify `.env` is in `.gitignore`

---

## 12. Testing and Monitoring **[HIGH]**

### What it is
Continuously validate that security controls are working as expected.

### Implementation checklist
- [ ] Write contract tests for all agent endpoints
- [ ] Add security-specific tests (RBAC, input validation, etc.)
- [ ] Run security smoke test before each release
- [ ] Monitor error rates, timeouts, and rate limit violations
- [ ] Set up alerts for security events (failed auth, access violations)
- [ ] Conduct quarterly security reviews

### Security smoke test
```bash
# Run before each release
pytest server/tests/test_security.py -v

# Should test:
# - RBAC enforcement (non-hosts cannot access hidden docs)
# - Input validation (oversized/malformed requests rejected)
# - Rate limiting (429 after exceeding limits)
# - Audit logging (all actions logged)
# - Content moderation (policy-violating content blocked)
```

### Monitoring alerts
Set up alerts for:
- Failed authentication attempts > 10/hour from single IP
- Rate limit violations > 100/hour
- Content moderation flags > 5/hour
- Agent error rates > 5%
- Unauthorized access attempts to hidden documents

### Testing
- Run full security test suite weekly
- Review monitoring dashboards daily (in production)
- Conduct penetration testing quarterly (recommended)

---

## 13. Implementation Priority

Implement guardrails in this order:

1. **Phase 1 - Critical (Before MVP)**
   - RBAC for hidden documents
   - Audit logging for all agent actions
   - Pydantic schema validation on all endpoints
   - Secrets hygiene (never commit secrets)

2. **Phase 2 - High (Before Production)**
   - Content moderation for LLM outputs
   - Rate limits on expensive operations
   - Scoped API tokens for all external services
   - Allowlists for external domains
   - Human-in-the-loop for risky actions

3. **Phase 3 - Medium (Production Hardening)**
   - Timeouts and circuit breakers
   - Egress network filtering
   - Advanced monitoring and alerting
   - Quarterly security reviews

---

## 14. Quick Reference

| Guardrail | Priority | Status | Docs Reference |
|-----------|----------|--------|----------------|
| RBAC | CRITICAL | ✅ Implemented | PROJECT_PLAN.md §9 |
| Audit Logging | CRITICAL | ⚠️ Partial (agent_events table exists) | AGENTS_SETUP.md §2.4 |
| Input Validation | CRITICAL | ⚠️ Partial (Pydantic in use) | - |
| Secrets Hygiene | CRITICAL | ✅ Documented | SECRET_MANAGEMENT.md |
| Content Moderation | HIGH | 🔲 Planned | LLM_IMAGE_CONFIG.md |
| Rate Limiting | HIGH | 🔲 Placeholder | See Section 6 |
| Allowlists | HIGH | 🔲 Planned | - |
| Human-in-Loop | HIGH | 🔲 Planned | - |
| Timeouts | MEDIUM | 🔲 Planned | - |
| Egress Filtering | MEDIUM | 🔲 Planned | - |

---

## 15. Additional Resources

- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **OWASP API Security**: https://owasp.org/www-project-api-security/
- **OpenAI Safety Best Practices**: https://platform.openai.com/docs/guides/safety-best-practices
- **FastAPI Security**: https://fastapi.tiangolo.com/tutorial/security/

---

_This checklist should be reviewed quarterly and after any security incidents. PM owns this document and is responsible for ensuring compliance._
