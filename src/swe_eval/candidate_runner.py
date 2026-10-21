"""Untrusted runner, executed ONLY in the candidate container, never a verdict."""
import contextlib
import importlib.util
import json
import sys


def main():
    request = json.loads(sys.stdin.read())
    source = request["input"]
    # Deliberate fd writes can still corrupt the protocol: fail closed.
    with contextlib.redirect_stdout(sys.stderr):
        spec = importlib.util.spec_from_file_location("candidate_intervals", "/workspace/intervals.py")
        candidate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(candidate)
        try:
            value = candidate.merge_ranges(source)
        except ValueError:
            response = {"error": "ValueError", "input_after": source}
        else:
            response = {"value": value, "input_after": source}
    sys.stdout.write(json.dumps(response, allow_nan=False))


if __name__ == "__main__":
    main()
