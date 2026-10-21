"""Trusted controller. NEVER import, mount or execute candidate code here.

The worker relays inputs to a separate socket-free candidate container. Only
assertions here establish correctness. Expected answers never enter that box.
"""
import json
import sys

CASES = [
    ("touching", [[1, 3], [3, 5]], [[1, 5]]),
    ("transitive", [[5, 8], [1, 3], [3, 5]], [[1, 8]]),
    ("disjoint_adjacent", [[1, 2], [3, 4]], [[1, 2], [3, 4]]),
    ("nested", [[1, 9], [2, 4], [9, 10]], [[1, 10]]),
    ("duplicates", [[2, 2], [2, 2]], [[2, 2]]),
    ("negative", [[-3, 0], [0, 2], [-8, -6]], [[-8, -6], [-3, 2]]),
    ("empty", [], []),
    ("input_not_mutated", [[3, 5], [1, 3]], [[1, 5]]),
    ("invalid", [[3, 1]], None),
]


def judge(observations):
    if not isinstance(observations, list) or len(observations) != len(CASES):
        raise ValueError("incomplete observations")
    details, executed, passed, errors = [], 0, 0, 0
    for (name, original, expected), observation in zip(CASES, observations):
        checks = 2 if name == "input_not_mutated" else 1
        if not isinstance(observation, dict) or set(observation) != {"response", "error"}:
            raise ValueError("invalid observation envelope")
        response = observation["response"]
        if observation["error"] is not None:
            errors += 1
            details.append({"case": name, "error": observation["error"], "passed": False})
            continue
        valid = isinstance(response, dict) and (
            set(response) == {"value", "input_after"} or set(response) == {"error", "input_after"})
        if not valid:
            errors += 1
            details.append({"case": name, "error": "malformed operation result", "passed": False})
            continue
        # Only JSON primitives cross the boundary, never candidate Python objects.
        executed += checks
        value_ok = (response.get("error") == "ValueError" if name == "invalid"
                    else "error" not in response and response.get("value") == expected)
        mutation_ok = name != "input_not_mutated" or response["input_after"] == original
        passed += int(value_ok) + (int(mutation_ok) if checks == 2 else 0)
        details.append({"case": name, "passed": value_ok and mutation_ok,
                        "expected": "ValueError" if name == "invalid" else expected,
                        "observed": response})
    expected_assertions = len(CASES) + 1
    return {"protocol": "swe-eval-grading-v2", "cases_expected": len(CASES),
            "cases_observed": len(observations), "assertions_expected": expected_assertions,
            "assertions_executed": executed, "assertions_passed": passed,
            "execution_errors": errors, "details": details,
            "passed": errors == 0 and executed == expected_assertions and passed == expected_assertions}


if __name__ == "__main__":
    if sys.argv[1:] == ["plan"]:
        print(json.dumps([{"input": source} for _, source, _ in CASES]))
    elif sys.argv[1:] == ["judge"]:
        print(json.dumps(judge(json.loads(sys.stdin.read())), allow_nan=False))
    else:
        raise SystemExit("expected plan or judge")
