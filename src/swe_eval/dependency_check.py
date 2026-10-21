"""Release gate for the explicitly supported mini DefaultAgent import closure.

Reports pip check's FAILURE, not a clean graph. Only the exact nine upstream
feature requirements below are exceptions. Any additional mismatch fails.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import tempfile
from importlib.metadata import version

EXCLUDED = {"datasets", "litellm", "openai", "prompt-toolkit", "pyyaml",
            "requests", "tenacity", "textual", "typer"}


def validate_lean_check(returncode: int, output: str):
    expected = {f"mini-swe-agent 2.4.6 requires {name}, which is not installed." for name in EXCLUDED}
    if returncode != 1 or set(output.strip().splitlines()) != expected:
        raise RuntimeError("dependency graph differs from the audited lean-agent exception")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lean-agent", action="store_true")
    args = parser.parse_args(argv)
    result = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True, timeout=60)
    if not args.lean_agent:
        print(result.stdout, end="")
        return result.returncode
    validate_lean_check(result.returncode, result.stdout)
    from .agent import verify_mini_api
    with tempfile.TemporaryDirectory(prefix="swe-dependencies-") as directory:
        previous = os.environ.get("MSWEA_GLOBAL_CONFIG_DIR")
        os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = directory
        try:
            verify_mini_api()
        finally:
            if previous is None:
                os.environ.pop("MSWEA_GLOBAL_CONFIG_DIR", None)
            else:
                os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = previous
    print(json.dumps({"status": "audited_lean_exception", "mini_version": version("mini-swe-agent"),
                      "pip_check": "FAILED_EXPECTED", "excluded": sorted(EXCLUDED),
                      "supported": "DefaultAgent with service model/environment adapters only"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
