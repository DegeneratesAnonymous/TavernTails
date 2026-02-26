"""Shared test configuration.

Sets ``TAVERNTAILS_SEED_DEV_USER=1`` so that tests that use ``server.main``
directly continue to work against the dev seed user (test@example.com / secret).
In production, set ``TAVERNTAILS_SEED_DEV_USER=0`` to disable this account.
"""

import os

os.environ.setdefault("TAVERNTAILS_SEED_DEV_USER", "1")
