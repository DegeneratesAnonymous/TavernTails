DevOps / Quartermaster Agent

Role:
- Maintain CI pipelines, reproducible test environments, caching, and deployment hooks.

Responsibilities:
- Ensure CI installs developer dependencies (tests, linters) and caches them.
- Provide simple commands to run contract tests locally and in CI.
- Coordinate with other agents to add necessary infra (secrets, runners).

Suggested Quick Tasks:
- Add `requirements-dev.txt` and pin `pytest`.
- Update CI workflows to install `requirements-dev.txt`.
- Add a `make test-contracts` shortcut or script.
