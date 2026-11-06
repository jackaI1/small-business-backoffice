"""Create the four linked tables in an empty base through Airtable's schema API."""

# Key is the first, primary, plain text field and the stable upsert identity.
SCHEMA = {
    "Assignees": [
        ("Key", "singleLineText"),
        ("Name", "singleLineText"),
        ("Email", "email"),
        ("CapacityHours", "number"),
    ],
    "Briefs": [
        ("Key", "singleLineText"),
        ("Name", "singleLineText"),
        ("Description", "multilineText"),
        ("Due", "date"),
        ("Status", "singleLineText"),
    ],
    "Deliverables": [
        ("Key", "singleLineText"),
        ("Name", "singleLineText"),
        ("Brief", "link:Briefs"),
        ("Assignee", "link:Assignees"),
        ("Start", "date"),
        ("Due", "date"),
        ("Hours", "number"),
        ("Status", "singleLineText"),
    ],
    "Approvals": [
        ("Key", "singleLineText"),
        ("Name", "singleLineText"),
        ("Deliverable", "link:Deliverables"),
        ("Assignee", "link:Assignees"),
        ("Due", "date"),
        ("Status", "singleLineText"),
    ],
}


def setup_tables(api):
    """Create only missing tables. Existing incompatible schemas fail before writes."""
    current = {t["name"]: t for t in api.schema_request("GET")["tables"]}
    for name, fields in SCHEMA.items():
        if name not in current:
            continue
        found = {f["name"]: f for f in current[name]["fields"]}
        for field, kind in fields:
            expected = "multipleRecordLinks" if kind.startswith("link:") else kind
            if field not in found or found[field]["type"] != expected:
                raise ValueError(f"Incompatible schema: {name}.{field}; use a fresh base")
            if kind.startswith("link:"):
                target = current.get(kind[5:], {}).get("id")
                if found[field].get("options", {}).get("linkedTableId") != target:
                    raise ValueError(f"Incompatible schema link: {name}.{field}")
    created = []
    for name, fields in SCHEMA.items():
        if name in current:
            continue
        definitions = []
        for field, kind in fields:
            definition = {"name": field, "type": kind}
            if kind.startswith("link:"):
                definition.update(
                    type="multipleRecordLinks", options={"linkedTableId": current[kind[5:]]["id"]}
                )
            elif kind == "number":
                definition["options"] = {"precision": 1}
            elif kind == "date":
                definition["options"] = {"dateFormat": {"name": "iso"}}
            definitions.append(definition)
        current[name] = api.schema_request("POST", {"name": name, "fields": definitions})
        created.append(name)
    return created
