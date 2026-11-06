"""Validate PBIR against Microsoft's published JSON schemas (network required).

Definitions and their references are fetched once per process. No report data is sent.
The regular pytest suite also checks the model's table, relationship and visual bindings offline.
"""

import json
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen

from jsonschema import Draft7Validator
from referencing import Registry, Resource


@lru_cache(maxsize=64)
def retrieve(uri):
    if not uri.startswith("https://developer.microsoft.com/json-schemas/"):
        raise ValueError(f"Unexpected schema host: {uri}")
    with urlopen(uri, timeout=30) as response:
        return Resource.from_contents(json.load(response))


def main():
    root = Path(__file__).resolve().parents[1] / "powerbi"
    registry = Registry(retrieve=retrieve)
    count = 0
    for path in sorted(root.rglob("*")):
        if path.suffix not in (".json", ".pbip", ".pbir", ".pbism"):
            continue
        data = json.loads(path.read_text())
        if "$schema" not in data:
            continue
        schema = retrieve(data["$schema"]).contents
        Draft7Validator(schema, registry=registry).validate(data)
        count += 1
    print(f"Validated {count} Power BI documents against Microsoft schemas")


if __name__ == "__main__":
    main()
