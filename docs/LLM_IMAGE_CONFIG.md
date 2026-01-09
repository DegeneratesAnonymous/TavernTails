# LLM and Image Generation Configuration Guide

This document provides budget-friendly default configurations for LLM and image generation services, along with cost-saving strategies for TavernTAIls development and production use.

## Budget-Friendly Defaults

### LLM Configuration (OpenAI GPT-4o-mini)

**Recommended Model**: `gpt-4o-mini`

**Why GPT-4o-mini?**
- Cost-effective: ~90% cheaper than GPT-4
- Fast response times: Better for real-time gameplay
- Sufficient quality: Great for narrative generation, NPC dialogue, scene analysis
- 128k context window: Handles campaign history and documents

**Pricing (as of 2024)**:
- Input: ~$0.15 per 1M tokens
- Output: ~$0.60 per 1M tokens
- Average cost per session: $0.01-0.05 (estimated)

**Configuration**:
```env
# .env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_TOKENS=500
OPENAI_TEMPERATURE=0.7
```

**Agent-Specific Settings**:
- **Narrative Agent**: temperature=0.7, max_tokens=500 (creative storytelling)
- **Scene Analysis**: temperature=0.3, max_tokens=200 (deterministic rules)
- **NPC Manager**: temperature=0.6, max_tokens=300 (consistent personalities)
- **Notes/Scribe**: temperature=0.2, max_tokens=400 (factual summaries)

### Image Generation Configuration (Stability AI SD3)

**Recommended Model**: `stable-diffusion-3-medium` or `sd3-turbo` (light)

**Why Stability SD3?**
- Affordable: ~$0.035-0.10 per image
- Quality: Good enough for scene illustrations and character portraits
- Fast: 1-3 seconds per image with Turbo
- Self-hostable: Can run locally for development

**Pricing (Stability API)**:
- SD3 Medium: ~$0.035 per image
- SD3 Turbo: ~$0.04 per image (faster)
- SD3 Large: ~$0.065 per image (higher quality)

**Configuration**:
```env
# .env
STABILITY_API_KEY=your_api_key_here
STABILITY_MODEL=sd3-turbo
STABILITY_IMAGE_SIZE=1024x1024
STABILITY_STEPS=20
```

**Alternative: Local Development**
For development, consider running Stable Diffusion locally:
- Use ComfyUI or Automatic1111 WebUI
- Free for unlimited images
- Requires GPU with 8GB+ VRAM
- Connect via local API endpoint

## Cost-Saving Strategies

### 1. Caching and Reuse

**LLM Response Caching**:
- Cache common prompts (world descriptions, recurring NPCs)
- Store generated content in session files
- Reuse narrative beats across similar scenes
- **Estimated Savings**: 40-60% of LLM costs

**Image Caching**:
- Cache images by scene + style hash
- Reuse character portraits across sessions
- Store in object storage (S3) with CDN
- **Estimated Savings**: 70-90% of image costs

**Implementation**:
```python
# Example caching strategy
@lru_cache(maxsize=1000)
def get_npc_description(npc_id: str, style: str) -> str:
    # Only call LLM if not cached
    pass
```

### 2. Rate Limiting and Quotas

**Per-User Quotas**:
- Limit LLM calls per session: 100-200 requests
- Limit images per session: 10-20 images
- Throttle rapid-fire requests (cooldown periods)

**Batch Processing**:
- Queue non-urgent requests (notes, summaries)
- Process in batches during off-peak hours
- Combine multiple small prompts into one larger prompt

**Configuration**:
```env
LLM_RATE_LIMIT_PER_MINUTE=30
LLM_MAX_CALLS_PER_SESSION=150
IMAGE_RATE_LIMIT_PER_HOUR=10
IMAGE_MAX_PER_SESSION=15
```

### 3. Fallback Strategies

**Model Downgrading**:
- Use GPT-4o-mini for most content
- Escalate to GPT-4o only for complex narratives
- Fall back to GPT-3.5-turbo if budget is exceeded

**Graceful Degradation**:
- Switch to template-based generation if API unavailable
- Use pre-generated content libraries
- Enable "low-cost mode" for budget-conscious users

**Local Models (Advanced)**:
- Run Llama 3.1, Mistral, or similar locally
- Free but requires infrastructure (GPU server)
- Good for development and self-hosted instances

### 4. Prompt Optimization

**Reduce Token Usage**:
- Keep prompts concise and focused
- Remove unnecessary context
- Use system messages for persistent instructions
- Compress campaign history (summarize old sessions)

**Example - Before**:
```python
prompt = f"""
You are the Narrative Agent for a D&D campaign. The campaign is called {campaign_name}.
Here is the full history: {entire_campaign_history}
Now generate a description for this scene: {scene}
Be creative and engaging.
"""
# ~2000 tokens
```

**Example - After**:
```python
prompt = f"""
Recent context: {last_3_turns}
Generate scene: {scene}
"""
# ~300 tokens (85% reduction)
```

### 5. Development vs Production

**Development Environment**:
- Use mock LLM responses for most testing
- Real API calls only for integration tests
- Local Stable Diffusion for image development
- **Cost**: ~$0-5/month

**Staging Environment**:
- Limited API quota for testing
- Shared API keys with rate limits
- Sample data instead of full production load
- **Cost**: ~$10-20/month

**Production Environment**:
- Full API access with monitoring
- Auto-scaling rate limits based on usage
- Reserved capacity for peak hours
- **Projected Cost**: ~$50-200/month (500-2000 active users)

## Environment Configuration

### Required API Keys

```env
# OpenAI (LLM)
OPENAI_API_KEY=sk-...
OPENAI_ORG_ID=org-...  # Optional

# Stability AI (Images)
STABILITY_API_KEY=sk-...

# Optional: Alternative Providers
ANTHROPIC_API_KEY=sk-...  # Claude (alternative LLM)
REPLICATE_API_TOKEN=r8_...  # Replicate (alternative images)
```

### Usage Monitoring

**Track Costs**:
```env
# Enable usage logging
ENABLE_USAGE_TRACKING=true
USAGE_LOG_PATH=/var/log/taverntails/usage.json

# Set budget alerts
MONTHLY_LLM_BUDGET_USD=100
MONTHLY_IMAGE_BUDGET_USD=50
ALERT_EMAIL=admin@taverntails.com
```

**Monitoring Endpoints**:
- `/admin/usage/llm` - LLM call statistics
- `/admin/usage/images` - Image generation stats
- `/admin/costs` - Estimated cost breakdown

## Cost Estimates

### Per-Session Estimates

| Feature | LLM Calls | Image Calls | Est. Cost |
|---------|-----------|-------------|-----------|
| Basic Session (2 hours) | 50 | 2 | $0.03 |
| Standard Session (4 hours) | 120 | 5 | $0.08 |
| Rich Session (4 hours + images) | 150 | 15 | $0.20 |

### Monthly Estimates (100 active users)

| Usage Level | Sessions/Month | LLM Cost | Image Cost | Total |
|-------------|----------------|----------|------------|-------|
| Light (casual play) | 200 | $6 | $4 | $10 |
| Medium (weekly games) | 800 | $30 | $20 | $50 |
| Heavy (daily play) | 2000 | $120 | $80 | $200 |

### Free Tier Strategy

**Offer Free Tier**:
- 10 LLM calls per session (enough for basic play)
- 1-2 images per session
- Text-only mode as default
- Upgrade to "Premium" for unlimited

**Premium Tier** ($5-10/month):
- Unlimited LLM calls (fair use)
- 50 images per month
- Priority API access
- Advanced agents (Storyboard, DM Helper)

## Best Practices

1. **Start Conservative**: Begin with strict rate limits and increase based on usage
2. **Monitor Constantly**: Track costs daily in early stages
3. **Cache Aggressively**: Most content can be reused
4. **Optimize Prompts**: Shorter prompts = lower costs
5. **Batch Requests**: Combine when possible
6. **Use Webhooks**: Async processing reduces timeout waste
7. **Plan for Scale**: Design for 10x growth
8. **Test Locally**: Use mocks and local models for development

## Troubleshooting

### API Rate Limits

**Problem**: 429 errors from OpenAI/Stability
**Solution**: 
- Implement exponential backoff
- Queue requests and process asynchronously
- Upgrade API tier if sustained high usage

### High Costs

**Problem**: Monthly bill exceeding budget
**Solution**:
- Review usage logs for anomalies
- Enable per-user quotas
- Reduce context window size
- Increase caching TTL

### Slow Response Times

**Problem**: Users waiting >5s for LLM responses
**Solution**:
- Switch to faster model (GPT-4o-mini Turbo)
- Reduce max_tokens
- Use streaming responses
- Pre-generate common content

## Resources

- [OpenAI Pricing](https://openai.com/pricing)
- [Stability AI Pricing](https://stability.ai/pricing)
- [OpenAI Best Practices](https://platform.openai.com/docs/guides/production-best-practices)
- [Prompt Engineering Guide](https://www.promptingguide.ai/)

---

_Last Updated: 2026-01-09 | Maintainer: TavernTAIls Core Team_
