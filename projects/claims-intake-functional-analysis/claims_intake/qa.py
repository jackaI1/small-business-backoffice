"""Conservative traceability aggregation used by the executable QA plan."""
def aggregate(requirement_ids, outcomes):
    rows = []
    for requirement in requirement_ids:
        linked = [o for o in outcomes if requirement in o["requirements"]]
        passed = bool(linked) and all(o["status"] == "PASS" for o in linked)
        rows.append({"id": requirement, "status": "PASS" if passed else "FAIL",
                     "tests": [o["test"] for o in linked]})
    return rows
