# Agent Setup and PM Oversight

_Last updated: 2026-01-09_

This document defines the setup, configuration, and Product Manager (PM) oversight responsibilities for TavernTAIls agents. It ensures that agents operate safely with appropriate safeguards, risk checks, and audit trails.

## 1. Agent Architecture Overview

TavernTAIls uses a multi-agent architecture where specialized AI agents handle different aspects of gameplay:

- **Narrative Agent**: Generates scene descriptions and story progression
- **Scene Analysis Agent**: Detects dice rolls and enforces game rules
- **NPC/Enemy Manager Agent**: Manages non-player characters and combat
- **Storyboard Agent**: Tracks campaign progress and story threads
- **Notes Agent**: Creates session recaps and summaries
- **Image Generation Agent**: Creates visual content for scenes
- **Player Agent**: Manages authentication, characters, and player data

Each agent operates independently but is coordinated by the **GM Orchestrator**, which validates outputs, enforces tone/safety policies, and publishes player-facing content.

## 2. PM Responsibilities and Oversight

The Product Manager (PM) or designated PM Agent owner is responsible for:

### 2.1 Safety and Risk Management
- **Enforce safety/risk checks**: Review all agent outputs for content policy violations, inappropriate content, or security risks before publication
- **Review security audits**: Conduct weekly reviews of the `agent_events` audit log to identify suspicious patterns, abuse, or policy violations
- **Maintain the safety checklist**: Own and update the safety checklist in `docs/AGENT_GUARDRAILS.md` as threats evolve
- **Incident response**: Coordinate response to security incidents, agent failures, or content moderation issues

### 2.2 Access Control and Gating
- **Gate risky actions**: Ensure high-impact actions require explicit approval:
  - Narrative publication (GM Orchestrator review)
  - Hidden document access (host/PM review required)
  - Campaign settings modifications (host approval)
  - User role changes (admin approval)
- **Maintain allowlists**: Keep allowlists current for:
  - Approved LLM/image generation providers
  - Egress network destinations
  - API endpoints available to agents
- **Role mappings**: Maintain RBAC role definitions (`player`, `host`, `admin`) and their associated permissions

### 2.3 Quality and Monitoring
- **Review agent performance**: Monitor agent response times, error rates, and output quality
- **Coordinate testing**: Ensure contract tests exist for all agent endpoints and payloads
- **Documentation ownership**: Keep agent setup documentation current and beginner-friendly
- **Budget oversight**: Monitor AI/LLM API usage and costs to prevent overruns

### 2.4 Weekly Audit Review Process
The PM should conduct weekly reviews following this checklist:

1. **Review `agent_events` table** for the past 7 days:
   - Check for unusual patterns (high failure rates, repeated errors)
   - Identify potential abuse (excessive API calls from single users)
   - Verify all high-risk actions were properly authorized

2. **Review access logs** for hidden documents:
   - Confirm only hosts accessed `visibility=hidden` documents
   - Investigate any unauthorized access attempts

3. **Check rate limiting and quotas**:
   - Verify no users exceeded rate limits
   - Adjust quotas if legitimate usage patterns emerge

4. **Content moderation review**:
   - Sample agent-generated narratives for policy violations
   - Update moderation rules based on findings

5. **Document findings**: Log review results in `PROGRESS.md` with date and any actions taken

## 3. Agent Configuration

### 3.1 Environment Variables
Agents are configured via environment variables (see `.env.example`):

```bash
# Agent behavior toggles
TAVERNTAILS_ENABLE_AI_AGENTS=false          # Set to true to enable LLM-powered agents
TAVERNTAILS_AGENT_TIMEOUT_SECONDS=30        # Timeout for agent operations
TAVERNTAILS_AGENT_MAX_RETRIES=2             # Retry attempts for failed agent calls

# Safety controls
TAVERNTAILS_ENABLE_CONTENT_MODERATION=true  # Enable content filtering
TAVERNTAILS_ENABLE_AUDIT_LOGGING=true       # Log all agent actions
TAVERNTAILS_RATE_LIMIT_ENABLED=false        # Enable rate limiting (placeholder)

# LLM provider settings
OPENAI_API_KEY=                              # OpenAI API key (if using OpenAI)
STABILITY_API_KEY=                           # Stability AI key (for image generation)
```

### 3.2 Agent Endpoint Security
All agent endpoints must:
- Require authentication (JWT token)
- Validate input with Pydantic schemas
- Log actions to `agent_events` table
- Return structured JSON responses
- Implement timeouts and circuit breakers

### 3.3 GM Orchestrator Review Gates
The GM Orchestrator enforces these review gates:

1. **Narrative publication**: All narrative content passes through content moderation before display
2. **Image generation**: Images are scanned for inappropriate content before caching
3. **NPC actions**: Combat-critical actions require scene state validation
4. **Document updates**: Hidden document changes require host role verification

## 4. Development and Testing

### 4.1 Local Development
1. Set `TAVERNTAILS_ENABLE_AI_AGENTS=false` in your `.env` to use deterministic stubs
2. Use `TAVERNTAILS_SEED_DEV_USER=1` to auto-create `test@example.com / secret`
3. Run `start-app.ps1` (Windows) or equivalent bash script to start backend + frontend

### 4.2 Agent Contract Tests
Each agent should have contract tests that verify:
- Input schema validation (Pydantic models)
- Output structure and field types
- Error handling and edge cases
- Authentication and authorization

Example test structure:
```python
def test_narrative_agent_contract():
    response = client.post("/narrative/generate", 
        json={"session_id": "test", "context": "..."})
    assert response.status_code == 200
    data = response.json()
    assert "narration" in data
    assert isinstance(data["narration"], str)
```

### 4.3 Smoke Testing
Before releases, run the full playthrough smoke test:
1. Create account → verify email → login
2. Create campaign → upload documents → create session
3. Send chat messages → trigger agent responses
4. Verify all responses logged to `agent_events`

## 5. Production Deployment

### 5.1 Pre-deployment Checklist
- [ ] All environment variables set in production secret store
- [ ] Rate limiting and audit logging enabled
- [ ] Content moderation configured with API keys
- [ ] Database migrations applied (`alembic upgrade head`)
- [ ] Secrets rotated per `docs/SECRET_MANAGEMENT.md` schedule
- [ ] PM has reviewed recent audit logs

### 5.2 Monitoring
Set up alerts for:
- Agent error rates > 5%
- Response times > 10 seconds
- Rate limit violations
- Content moderation flags
- Unauthorized access attempts

### 5.3 Incident Response
If an agent security incident occurs:
1. Immediately disable affected agent via feature flag
2. Review `agent_events` and access logs to determine scope
3. Notify PM and security team
4. Document incident in `PROGRESS.md`
5. Deploy fix and re-enable after PM approval

## 6. References

- **Guardrails**: See `docs/AGENT_GUARDRAILS.md` for detailed safety checklist
- **LLM Configuration**: See `docs/LLM_IMAGE_CONFIG.md` for AI provider setup
- **Secret Management**: See `docs/SECRET_MANAGEMENT.md` for key rotation procedures
- **Project Plan**: See `PROJECT_PLAN.md` Section 9 for security architecture
- **Agents Overview**: See `AGENTS.md` for agent roles and responsibilities

---

_This document should be reviewed and updated monthly by the PM. Update the "Last updated" stamp with each revision._
