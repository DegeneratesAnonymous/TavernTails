"""Fail CI for new mypy diagnostics while keeping existing debt visible."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tools/mypy_baseline.json"
ERROR = re.compile(r"^(.*?):\d+(?::\d+)?: error: (.*)$")


def diagnostics(output: str) -> Counter[tuple[str, str]]:
    result: Counter[tuple[str, str]] = Counter()
    for line in output.splitlines():
        match = ERROR.match(line)
        if match:
            # A moved definition can change both the diagnostic's position and
            # a line reference inside its message. Neither is a new error.
            message = re.sub(r"\bon line \d+\b", "on line <n>", match[2])
            result[(match[1].replace("\\", "/"), message)] += 1
    return result


def new_diagnostics(output: str, entries: list[dict]) -> Counter[tuple[str, str]]:
    known = Counter({(entry["path"], entry["message"]): entry["count"] for entry in entries})
    return diagnostics(output) - known


def main() -> int:
    baseline = json.loads(BASELINE.read_text())
    with tempfile.TemporaryDirectory(prefix="taverntails-mypy-") as cache:
        result = subprocess.run([
            sys.executable, "-m", "mypy", "server", "--exclude", "server/agents/archive",
            "--ignore-missing-imports", "--check-untyped-defs", "--python-version", "3.11",
            "--no-pretty", "--no-error-summary", "--no-incremental", "--cache-dir", cache,
        ], cwd=ROOT, capture_output=True, text=True)
    if result.returncode not in (0, 1) or result.returncode == 1 and not diagnostics(result.stdout):
        print(result.stdout + result.stderr)
        return 2  # tool/config/import failure must never masquerade as a pass
    added = new_diagnostics(result.stdout, baseline["diagnostics"])
    current_count = sum(diagnostics(result.stdout).values())
    print(f"mypy: {current_count} current diagnostics; {sum(added.values())} new.")
    for (path, message), count in sorted(added.items()):
        print(f"{path}: {message} (count {count})")
    return 1 if added else 0


if __name__ == "__main__":
    sys.exit(main())
