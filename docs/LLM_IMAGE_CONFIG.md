# LLM and Image Generation Configuration

_Last updated: 2026-01-09_

This document provides configuration guidance for integrating Large Language Models (LLMs) and image generation services into TavernTAIls agents. It covers provider setup, safety considerations, and best practices for efficient and secure usage.

## Quick Start

1. **Choose your providers**: OpenAI (LLM), Stability AI (images), or alternatives
2. **Set environment variables**: Add API keys to `.env` (never commit them!)
3. **Enable content moderation**: Set `TAVERNTAILS_ENABLE_CONTENT_MODERATION=true`
4. **Configure caching**: Enable response caching to reduce costs
5. **Test in dev mode**: Use stubs (`TAVERNTAILS_ENABLE_AI_AGENTS=false`) before enabling real AI

---

## 1. LLM Provider Configuration

### 1.1 Supported Providers

TavernTAIls supports multiple LLM providers:

| Provider | Best For | Cost | Setup Difficulty |
|----------|----------|------|-----------------|
| **OpenAI** (GPT-4, GPT-3.5) | High-quality narrative, general purpose | $$ | Easy |
| **Anthropic** (Claude) | Long context, detailed analysis | $$ | Easy |
| **Local models** (Ollama, LM Studio) | Privacy, offline, no API costs | Free | Medium |
| **Azure OpenAI** | Enterprise compliance | $$$ | Hard |

### 1.2 Environment Variables

Add to your `.env` file:

```bash
# LLM Provider Selection
TAVERNTAILS_LLM_PROVIDER=openai  # Options: openai, anthropic, local, azure

# OpenAI Configuration
OPENAI_API_KEY=sk-...            # Get from https://platform.openai.com/api-keys
OPENAI_MODEL=gpt-3.5-turbo       # Or gpt-4, gpt-4-turbo
OPENAI_MAX_TOKENS=1000           # Max tokens per request
OPENAI_TEMPERATURE=0.7           # Creativity (0.0-1.0)

# Anthropic Configuration
ANTHROPIC_API_KEY=sk-ant-...     # Get from https://console.anthropic.com/
ANTHROPIC_MODEL=claude-3-sonnet  # Or claude-3-opus, claude-3-haiku

# Local Model Configuration
LOCAL_LLM_URL=http://localhost:11434/api/generate  # Ollama endpoint
LOCAL_LLM_MODEL=llama2           # Model name

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-35-turbo
```

### 1.3 Safety: Never Send Secrets to LLMs

**⚠️ CRITICAL: Never include secrets in LLM prompts or context**

LLMs may:
- Log your inputs for training or debugging
- Accidentally return secrets in responses
- Be compromised or have data breaches

**Before sending data to an LLM:**
- [ ] Strip all environment variables from context
- [ ] Remove API keys, tokens, passwords
- [ ] Redact database connection strings
- [ ] Remove user email addresses (unless necessary for the task)
- [ ] Filter out internal system paths and configuration

**Example: Safe vs Unsafe**
```python
# ❌ UNSAFE - Sending secrets to LLM
context = f"""
Campaign settings:
Database: {os.getenv('DATABASE_URL')}
API Key: {os.getenv('OPENAI_API_KEY')}
"""

# ✅ SAFE - Secrets removed
context = f"""
Campaign settings:
Database: [REDACTED]
API Key: [REDACTED]
"""
```

### 1.4 Content Moderation

**Always enable content moderation** to filter inappropriate AI-generated content.

```bash
# In .env
TAVERNTAILS_ENABLE_CONTENT_MODERATION=true
```

**Moderation API Options:**
- **OpenAI Moderation API** (Free, fast, recommended)
- **Perspective API** (Google, free)
- **Azure Content Safety** (Enterprise)

**Implementation example:**
```python
import openai

async def moderate_content(text: str) -> tuple[bool, str]:
    """
    Returns (is_safe, reason).
    is_safe=True means content passes moderation.
    """
    try:
        response = await openai.Moderation.acreate(input=text)
        result = response["results"][0]
        
        if result["flagged"]:
            categories = [cat for cat, flagged in result["categories"].items() if flagged]
            return False, f"Flagged for: {', '.join(categories)}"
        
        return True, "OK"
    except Exception as e:
        logger.error(f"Moderation API error: {e}")
        # Fail open or closed depending on your policy
        return True, "Moderation check failed (allowed)"

# Use in agent
async def generate_narrative(request: NarrativeRequest):
    raw_output = await call_llm(request.context)
    
    is_safe, reason = await moderate_content(raw_output)
    if not is_safe:
        logger.warning(f"Content moderation blocked narrative: {reason}")
        return {"narration": "The narrator pauses, reconsidering their words..."}
    
    return {"narration": raw_output}
```

**Test moderation with known policy violations:**
```python
# Should be flagged
test_cases = [
    "explicit violence here",
    "hate speech here",
    "self-harm content here"
]

for test in test_cases:
    is_safe, reason = await moderate_content(test)
    assert not is_safe, f"Should flag: {test}"
```

---

## 2. Image Generation Configuration

### 2.1 Supported Providers

| Provider | Best For | Cost | Quality |
|----------|----------|------|---------|
| **Stability AI** (Stable Diffusion) | Flexible, good quality | $ | High |
| **DALL-E** (OpenAI) | Easy setup, consistent style | $$ | High |
| **Midjourney** (API) | Artistic, detailed | $$$ | Highest |
| **Local** (Stable Diffusion, ComfyUI) | Privacy, offline | Free | Medium-High |

### 2.2 Environment Variables

```bash
# Image Provider Selection
TAVERNTAILS_IMAGE_PROVIDER=stability  # Options: stability, dalle, midjourney, local

# Stability AI Configuration
STABILITY_API_KEY=sk-...              # Get from https://platform.stability.ai/
STABILITY_MODEL=stable-diffusion-xl   # Model variant
STABILITY_STYLE=fantasy               # Default style preset

# DALL-E Configuration
OPENAI_API_KEY=sk-...                 # Same as LLM if using OpenAI
DALLE_MODEL=dall-e-3                  # Or dall-e-2
DALLE_SIZE=1024x1024                  # Image dimensions
DALLE_QUALITY=standard                # Or 'hd'

# Local Stable Diffusion
LOCAL_SD_URL=http://localhost:7860/api/txt2img
LOCAL_SD_MODEL=sd_xl_base_1.0
```

### 2.3 Safety: Image Moderation

Images should also be checked for policy violations:

```bash
# Enable image safety checks
TAVERNTAILS_ENABLE_IMAGE_MODERATION=true
```

**Options:**
- **Stability AI Safety Classifier** (built-in)
- **Azure Content Safety** (for images)
- **Google Cloud Vision API** (safe search detection)

**Implementation:**
```python
async def generate_scene_image(prompt: str, session_id: str):
    # Generate image
    image_url = await stability_api.generate(prompt)
    
    # Check image safety (if enabled)
    if os.getenv("TAVERNTAILS_ENABLE_IMAGE_MODERATION") == "true":
        is_safe = await check_image_safety(image_url)
        if not is_safe:
            logger.warning(f"Image moderation blocked: {prompt}")
            # Return placeholder or re-generate with safer prompt
            return {"image_url": "/images/placeholder.png"}
    
    # Cache for reuse
    cached_url = await cache_image(image_url, session_id, prompt)
    return {"image_url": cached_url}
```

---

## 3. Response Caching

**Caching reduces costs and improves performance** by reusing previous responses.

### 3.1 Enable Caching

```bash
# In .env
TAVERNTAILS_ENABLE_RESPONSE_CACHING=true
TAVERNTAILS_CACHE_TTL_SECONDS=3600    # Cache for 1 hour
TAVERNTAILS_CACHE_MAX_SIZE_MB=500     # Max cache size
```

### 3.2 What to Cache

| Content Type | Cache Strategy | TTL |
|--------------|---------------|-----|
| **Narrative scenes** | Cache by (session_id, scene_context_hash) | 1 hour |
| **NPC profiles** | Cache by npc_id (invalidate on stats change) | 24 hours |
| **Images** | Cache by (prompt_hash, style) permanently | Permanent |
| **Scene analysis** | Don't cache (real-time state) | N/A |

### 3.3 Implementation Example

```python
import hashlib
import json
from datetime import datetime, timedelta

# Simple in-memory cache (use Redis in production)
_cache = {}

def cache_key(prefix: str, **kwargs) -> str:
    """Generate cache key from parameters."""
    data = json.dumps(kwargs, sort_keys=True)
    hash_val = hashlib.sha256(data.encode()).hexdigest()[:16]
    return f"{prefix}:{hash_val}"

async def get_cached_narrative(session_id: str, context: str):
    """Try to get cached narrative."""
    key = cache_key("narrative", session_id=session_id, context=context)
    
    if key in _cache:
        cached, expires_at = _cache[key]
        if datetime.utcnow() < expires_at:
            logger.info(f"Cache hit: {key}")
            return cached
        else:
            del _cache[key]  # Expired
    
    return None

async def cache_narrative(session_id: str, context: str, response: dict):
    """Cache narrative response."""
    key = cache_key("narrative", session_id=session_id, context=context)
    ttl = int(os.getenv("TAVERNTAILS_CACHE_TTL_SECONDS", "3600"))
    expires_at = datetime.utcnow() + timedelta(seconds=ttl)
    
    _cache[key] = (response, expires_at)
    logger.info(f"Cached: {key} (expires in {ttl}s)")

# Use in agent
async def generate_narrative(request: NarrativeRequest):
    # Try cache first
    cached = await get_cached_narrative(request.session_id, request.context)
    if cached:
        return cached
    
    # Generate new response
    response = await call_llm(request.context)
    
    # Cache for reuse
    await cache_narrative(request.session_id, request.context, response)
    
    return response
```

### 3.4 Image Caching

Images should be cached permanently to avoid regeneration costs:

```python
async def cache_image(url: str, session_id: str, prompt: str) -> str:
    """
    Download image and cache locally or in S3.
    Returns cached URL.
    """
    # Generate deterministic filename
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    filename = f"{session_id}_{prompt_hash}.png"
    
    # Download and save
    image_data = await download_image(url)
    
    if os.getenv("TAVERNTAILS_STORAGE_MODE") == "s3":
        cached_url = await upload_to_s3(filename, image_data)
    else:
        path = f"server/sessions/{session_id}/images/{filename}"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(image_data)
        cached_url = f"/sessions/{session_id}/images/{filename}"
    
    return cached_url
```

---

## 4. Cost Management

### 4.1 Monitor Usage

Track costs to avoid overruns:

```python
# Log all LLM/image API calls
async def log_api_usage(agent: str, tokens: int, cost: float):
    event = AgentEvent(
        agent=agent,
        action="api_call",
        details=json.dumps({"tokens": tokens, "cost": cost})
    )
    db.add(event)
    await db.commit()

# Calculate cost
async def call_llm_with_logging(prompt: str):
    response = await openai.ChatCompletion.acreate(...)
    
    tokens = response["usage"]["total_tokens"]
    cost = estimate_cost(tokens, model="gpt-3.5-turbo")
    
    await log_api_usage("narrative", tokens, cost)
    
    return response
```

### 4.2 Set Budget Limits

```bash
# In .env
TAVERNTAILS_MAX_MONTHLY_SPEND_USD=100  # Alert if exceeded
TAVERNTAILS_MAX_TOKENS_PER_USER=10000  # Per month
```

### 4.3 Cost Optimization Tips

1. **Use cheaper models for simple tasks**: GPT-3.5 for notes, GPT-4 for complex narrative
2. **Reduce max_tokens**: Set lower limits for summaries and quick responses
3. **Cache aggressively**: Especially for images and NPC profiles
4. **Batch requests**: Combine multiple prompts when possible
5. **Use local models for dev**: Only use paid APIs in staging/production

---

## 5. Testing AI Integration

### 5.1 Dev Mode (Stubs)

Test without real API calls:

```bash
# In .env
TAVERNTAILS_ENABLE_AI_AGENTS=false  # Use deterministic stubs
```

**Stub implementation:**
```python
async def generate_narrative_stub(request: NarrativeRequest):
    """Deterministic stub for testing."""
    return {
        "narration": f"[STUB] Scene unfolds in {request.session_id}...",
        "suggestions": ["Investigate", "Talk to NPC", "Rest"],
        "timestamp": datetime.utcnow().isoformat()
    }

async def generate_narrative(request: NarrativeRequest):
    if os.getenv("TAVERNTAILS_ENABLE_AI_AGENTS") != "true":
        return await generate_narrative_stub(request)
    
    # Real AI call
    return await call_llm(request.context)
```

### 5.2 Contract Tests

Ensure responses match expected schema:

```python
def test_narrative_contract():
    """Test that narrative response has required fields."""
    response = client.post("/narrative/generate", json={
        "session_id": "test",
        "context": "The party enters a tavern"
    })
    
    assert response.status_code == 200
    data = response.json()
    
    # Required fields
    assert "narration" in data
    assert isinstance(data["narration"], str)
    assert len(data["narration"]) > 0
    
    # Optional fields
    if "suggestions" in data:
        assert isinstance(data["suggestions"], list)
```

### 5.3 Safety Tests

Test that safety controls work:

```python
async def test_content_moderation():
    """Test that inappropriate content is blocked."""
    unsafe_prompt = "Generate a scene with explicit violence..."
    
    response = await generate_narrative(NarrativeRequest(
        session_id="test",
        context=unsafe_prompt
    ))
    
    # Should return safe fallback
    assert "pauses, reconsidering" in response["narration"].lower()

async def test_secrets_not_sent():
    """Test that secrets are stripped from context."""
    context_with_secrets = f"""
    Campaign: Test
    Database: {os.getenv('DATABASE_URL')}
    """
    
    sanitized = await sanitize_context(context_with_secrets)
    
    assert "DATABASE_URL" not in sanitized
    assert os.getenv("DATABASE_URL") not in sanitized
```

---

## 6. Production Deployment

### 6.1 Pre-deployment Checklist

Before enabling AI in production:

- [ ] API keys stored in secret manager (not `.env` file)
- [ ] Content moderation enabled and tested
- [ ] Response caching enabled
- [ ] Cost monitoring and alerts configured
- [ ] Rate limiting enabled (see `docs/AGENT_GUARDRAILS.md`)
- [ ] Audit logging enabled for all API calls
- [ ] Secrets sanitization tested
- [ ] Fallback responses ready for API failures
- [ ] Budget limits configured and enforced

### 6.2 Monitoring

Set up alerts for:
- API error rate > 5%
- Cost exceeds $X per day
- Moderation flags > 10 per hour
- API latency > 10 seconds

### 6.3 Incident Response

If AI APIs fail:
1. Fall back to stub responses (don't block gameplay)
2. Log error to `agent_events` table
3. Alert PM/on-call engineer
4. Display user-friendly message: "The narrator is taking a break. Try again in a moment."

---

## 7. Privacy and Compliance

### 7.1 Data Retention

**LLM providers may retain your inputs** (check their policies):
- OpenAI: 30 days (can opt out of training)
- Anthropic: Not used for training
- Local models: Complete privacy

### 7.2 User Data Protection

**Never send PII to LLMs unless necessary:**
- Strip email addresses
- Anonymize user names (use IDs instead)
- Redact real-world locations if using player data

### 7.3 Compliance

If subject to GDPR/CCPA:
- [ ] Document what data is sent to AI providers
- [ ] Add to privacy policy
- [ ] Provide opt-out mechanism
- [ ] Implement data deletion requests

---

## 8. Additional Resources

- **OpenAI Best Practices**: https://platform.openai.com/docs/guides/production-best-practices
- **Stability AI Docs**: https://platform.stability.ai/docs
- **LangChain** (abstraction layer): https://python.langchain.com/
- **Prompt Engineering Guide**: https://www.promptingguide.ai/

---

## 9. Quick Reference

| Task | Environment Variable | Default |
|------|---------------------|---------|
| Enable AI agents | `TAVERNTAILS_ENABLE_AI_AGENTS` | `false` |
| Content moderation | `TAVERNTAILS_ENABLE_CONTENT_MODERATION` | `true` |
| Response caching | `TAVERNTAILS_ENABLE_RESPONSE_CACHING` | `false` |
| Image moderation | `TAVERNTAILS_ENABLE_IMAGE_MODERATION` | `true` |
| LLM provider | `TAVERNTAILS_LLM_PROVIDER` | `openai` |
| Image provider | `TAVERNTAILS_IMAGE_PROVIDER` | `stability` |
| OpenAI API key | `OPENAI_API_KEY` | (required) |
| Stability API key | `STABILITY_API_KEY` | (required) |

---

_This document should be updated whenever new AI providers are added or safety requirements change. PM owns this document._
