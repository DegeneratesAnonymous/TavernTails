# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main` branch | ✅ Active |
| `develop` branch | ✅ Active |
| Older releases | ❌ No |

## Reporting a Vulnerability

**Please do not file a public GitHub issue for security vulnerabilities.**

To report a vulnerability, please use one of the following private channels:

1. **GitHub Private Security Advisory** — [Report a vulnerability](../../security/advisories/new) via the "Security" tab of this repository.
2. **Direct contact** — Reach out to a repository maintainer listed in `CODEOWNERS`.

### What to include

- A clear description of the vulnerability and the affected component
- Steps to reproduce (or a proof-of-concept, if safe to share)
- The potential impact (data exposure, auth bypass, etc.)
- Your suggested remediation, if any

### Response timeline

- **Acknowledgement:** within 3 business days
- **Initial assessment:** within 7 business days
- **Fix / mitigation:** timeline communicated after initial assessment

### Scope

In-scope vulnerabilities include:
- Authentication or authorisation bypass (JWT, RBAC)
- SQL injection or other injection vulnerabilities
- Sensitive data exposure (PII, tokens, secrets)
- Remote code execution
- Cross-site scripting (XSS) in the React frontend
- Insecure direct object reference (IDOR) on campaign/character data

Out of scope:
- Vulnerabilities in dependencies (please report these to the upstream maintainer; we track them via Dependabot)
- Theoretical vulnerabilities with no practical exploit path
- Issues that require physical access to the host

## Security Best Practices for Contributors

- Never commit secrets, API keys, or credentials to the repository
- Use environment variables for all configuration values (see `docs/SECRET_MANAGEMENT.md`)
- All new endpoints must have authentication/authorisation checks (`Depends(require_auth)`)
- Validate and sanitise all user-supplied input
- Follow the security review checklist in `.github/agents/Security.agent.md`
