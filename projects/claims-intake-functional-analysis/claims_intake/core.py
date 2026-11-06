"""Deterministic intake rules and a transactional SQLite review queue."""
import hashlib
import json
import sqlite3
from datetime import date


FIELDS = {"claim_ref", "policy_id", "property_id", "loss_date", "reported_date",
          "loss_type", "amount_cents", "description", "evidence"}
REQUIRED = FIELDS - {"evidence"}
LOSS_TYPES = {"water", "fire", "theft", "wind"}
EVIDENCE = {"water": {"photos"}, "fire": {"photos"},
            "theft": {"inventory", "police_reference"}, "wind": {"photos"}}
HIGH_VALUE_CENTS = 2_500_000
ACTIONS = {"request_information", "refer_adjuster", "close_duplicate"}


class InputError(ValueError):
    """An invalid batch envelope, rather than an incomplete claim."""


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("Expected an ISO date")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Expected YYYY-MM-DD")
    return parsed


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS policies (
            policy_id TEXT PRIMARY KEY, property_id TEXT NOT NULL,
            start_date TEXT NOT NULL, end_date TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY, claim_ref TEXT NOT NULL,
            fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('READY_FOR_ADJUSTER','NEEDS_REVIEW')),
            reasons TEXT NOT NULL, evaluated_on TEXT NOT NULL,
            UNIQUE(claim_ref, fingerprint)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, claim_id INTEGER NOT NULL REFERENCES claims(id),
            kind TEXT NOT NULL, actor TEXT NOT NULL, details TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE IF NOT EXISTS reviews (
            claim_id INTEGER PRIMARY KEY REFERENCES claims(id),
            action TEXT NOT NULL, reviewer TEXT NOT NULL
        );
    """)
    return db


def seed_policies(db, policies):
    """Insert an immutable policy snapshot; conflicting replacement is an error."""
    if not isinstance(policies, list):
        raise InputError("Policy snapshot must be an array")
    with db:
        for p in policies:
            if not isinstance(p, dict) or set(p) != {"policy_id", "property_id", "start_date", "end_date"}:
                raise InputError("Invalid policy fields")
            if not all(isinstance(v, str) and v.strip() for v in p.values()):
                raise InputError("Invalid policy values")
            if parse_date(p["start_date"]) > parse_date(p["end_date"]):
                raise InputError("Invalid policy interval")
            values = tuple(p[k] for k in ("policy_id", "property_id", "start_date", "end_date"))
            old = db.execute("SELECT * FROM policies WHERE policy_id=?", (p["policy_id"],)).fetchone()
            if old and tuple(old) != values:
                raise InputError("Policy snapshot cannot be replaced")
            db.execute("INSERT OR IGNORE INTO policies VALUES (?,?,?,?)", values)


def validate_batch(claims):
    if not isinstance(claims, list) or not claims:
        raise InputError("Claims must be a non-empty JSON array")
    for c in claims:
        if not isinstance(c, dict) or set(c) - FIELDS:
            raise InputError("Each claim must be an object with documented fields only")
        if not isinstance(c.get("claim_ref"), str) or not c["claim_ref"].strip():
            raise InputError("Each claim needs a non-blank string claim_ref for tracking")
        try:
            json.dumps(c, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise InputError("Claims must contain finite JSON values") from exc


def evaluate(db, c, as_of):
    reasons = []
    missing = sorted(k for k in REQUIRED if c.get(k) is None or
                     (isinstance(c.get(k), str) and not c[k].strip()))
    reasons.extend("MISSING:" + k for k in missing)
    for field in ("policy_id", "property_id", "description"):
        if field not in missing and not isinstance(c.get(field), str):
            reasons.append("INVALID:" + field)
    policy_id = c.get("policy_id")
    policy = db.execute("SELECT * FROM policies WHERE policy_id=?", (policy_id,)).fetchone() \
        if isinstance(policy_id, str) else None
    if "policy_id" not in missing and not policy:
        reasons.append("UNKNOWN_POLICY")
    if policy and "property_id" not in missing and c.get("property_id") != policy["property_id"]:
        reasons.append("PROPERTY_MISMATCH")
    dates = {}
    for field in ("loss_date", "reported_date"):
        if field not in missing:
            try:
                dates[field] = parse_date(c.get(field))
            except (ValueError, TypeError):
                reasons.append("INVALID:" + field)
    loss, reported = dates.get("loss_date"), dates.get("reported_date")
    if loss and policy and not parse_date(policy["start_date"]) <= loss <= parse_date(policy["end_date"]):
        reasons.append("LOSS_OUTSIDE_POLICY")
    if loss and reported and loss > reported:
        reasons.append("LOSS_AFTER_REPORT")
    if (loss and loss > as_of) or (reported and reported > as_of):
        reasons.append("FUTURE_DATE")
    loss_type = c.get("loss_type")
    valid_type = isinstance(loss_type, str) and loss_type in LOSS_TYPES
    if "loss_type" not in missing and not valid_type:
        reasons.append("INVALID:loss_type")
    amount = c.get("amount_cents")
    if "amount_cents" not in missing:
        if type(amount) is not int or amount <= 0 or amount > 1_000_000_000:
            reasons.append("INVALID:amount_cents")
        elif amount >= HIGH_VALUE_CENTS:
            reasons.append("HIGH_VALUE")
    evidence = c.get("evidence", [])
    if not isinstance(evidence, list) or not all(isinstance(x, str) and x.strip() for x in evidence):
        reasons.append("INVALID:evidence")
    elif valid_type:
        reasons.extend("EVIDENCE_REQUIRED:" + e for e in sorted(EVIDENCE[loss_type] - set(evidence)))
    # Compare only valid matching fields; malformed records cannot crash routing.
    for row in db.execute("SELECT claim_ref, payload FROM claims"):
        other = json.loads(row["payload"])
        if row["claim_ref"] == c["claim_ref"]:
            reasons.append("REFERENCE_CONFLICT")
        elif policy and loss and valid_type and all(other.get(k) == c.get(k)
                 for k in ("policy_id", "loss_date", "loss_type")):
            reasons.append("POSSIBLE_DUPLICATE")
    return sorted(set(reasons))


def intake(db, claims, as_of):
    """Commit a whole batch or none. Identical retries return the original decision."""
    if not isinstance(as_of, date):
        raise InputError("as_of must be a date")
    validate_batch(claims)
    results = []
    # BEGIN IMMEDIATE serializes duplicate detection with writes across processes.
    try:
        db.execute("BEGIN IMMEDIATE")
        for c in claims:
            payload = json.dumps(c, sort_keys=True, separators=(",", ":"), allow_nan=False)
            fingerprint = hashlib.sha256(payload.encode()).hexdigest()
            old = db.execute("SELECT * FROM claims WHERE claim_ref=? AND fingerprint=?",
                             (c["claim_ref"], fingerprint)).fetchone()
            if old:
                results.append({**dict(old), "replayed": True})
                continue
            reasons = evaluate(db, c, as_of)
            status = "NEEDS_REVIEW" if reasons else "READY_FOR_ADJUSTER"
            cursor = db.execute("""INSERT INTO claims
                (claim_ref,fingerprint,payload,status,reasons,evaluated_on) VALUES (?,?,?,?,?,?)""",
                (c["claim_ref"], fingerprint, payload, status, json.dumps(reasons), as_of.isoformat()))
            claim_id = cursor.lastrowid
            db.execute("INSERT INTO events(claim_id,kind,actor,details) VALUES (?,?,?,?)",
                       (claim_id, "INTAKE", "rules-v1", json.dumps({"status": status, "reasons": reasons})))
            row = db.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
            results.append({**dict(row), "replayed": False})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return results


def queue(db):
    return [dict(r) for r in db.execute("""SELECT c.id,c.claim_ref,c.status,c.reasons,c.evaluated_on
        FROM claims c LEFT JOIN reviews r ON r.claim_id=c.id
        WHERE c.status='NEEDS_REVIEW' AND r.claim_id IS NULL ORDER BY c.id""")]


def detail(db, claim_id):
    row = db.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    if not row:
        raise InputError("Claim not found")
    record = dict(row)
    record["payload"] = json.loads(record["payload"])
    record["reasons"] = json.loads(record["reasons"])
    record["events"] = [dict(e) for e in db.execute(
        "SELECT kind,actor,details,created_at FROM events WHERE claim_id=? ORDER BY id", (claim_id,))]
    for event in record["events"]:
        event["details"] = json.loads(event["details"])
    action = db.execute("SELECT action,reviewer FROM reviews WHERE claim_id=?", (claim_id,)).fetchone()
    record["review"] = dict(action) if action else None
    c = record["payload"]
    record["related_ids"] = []
    for other in db.execute("SELECT id,claim_ref,payload FROM claims WHERE id<>? ORDER BY id", (claim_id,)):
        payload = json.loads(other["payload"])
        if other["claim_ref"] == c["claim_ref"] or all(c.get(k) is not None and c.get(k) == payload.get(k)
                for k in ("policy_id", "loss_date", "loss_type")):
            record["related_ids"].append(other["id"])
    return record


def review(db, claim_id, action, reviewer):
    if action not in ACTIONS or not isinstance(reviewer, str) or not reviewer.strip():
        raise InputError("Use a documented action and a non-blank reviewer ID")
    with db:
        db.execute("BEGIN IMMEDIATE")
        claim = db.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if not claim or claim["status"] != "NEEDS_REVIEW":
            raise InputError("Only a flagged claim can be reviewed")
        if db.execute("SELECT 1 FROM reviews WHERE claim_id=?", (claim_id,)).fetchone():
            raise InputError("Claim already reviewed")
        if action == "close_duplicate" and not set(json.loads(claim["reasons"])) & {
                "POSSIBLE_DUPLICATE", "REFERENCE_CONFLICT"}:
            raise InputError("Closing as duplicate needs a duplicate or reference flag")
        db.execute("INSERT INTO reviews VALUES (?,?,?)", (claim_id, action, reviewer))
        db.execute("INSERT INTO events(claim_id,kind,actor,details) VALUES (?,?,?,?)",
                   (claim_id, "REVIEW", reviewer, json.dumps({"action": action})))


def summary(db):
    counts = {r["status"]: r["n"] for r in db.execute("SELECT status,COUNT(*) n FROM claims GROUP BY status")}
    return {"total": sum(counts.values()), "ready_for_adjuster": counts.get("READY_FOR_ADJUSTER", 0),
            "flagged": counts.get("NEEDS_REVIEW", 0), "awaiting_review": len(queue(db)),
            "reviewed": db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]}
