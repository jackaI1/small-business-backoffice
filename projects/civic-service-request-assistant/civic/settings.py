import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

DATA = Path(__file__).parent / "data"
CONFIG = json.loads((DATA / "app.json").read_text())
HANDBOOK = json.loads((DATA / "handbook.json").read_text())


def local_url(url: str) -> str:
    parts = urlsplit(url)
    if (
        parts.scheme != "http"
        or parts.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            "This demo permits only loopback HTTP services; no cloud models or exports."
        )
    return url.rstrip("/")


@dataclass
class Settings:
    db: str = field(default_factory=lambda: os.getenv("CIVIC_DB", "requests.sqlite3"))
    staff_token: str = field(default_factory=lambda: os.getenv("CIVIC_STAFF_TOKEN", ""))
    ollama_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    )
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b"))
    graph_url: str = field(
        default_factory=lambda: os.getenv("GRAPH_BASE_URL", "http://127.0.0.1:8091/v1.0")
    )
    graph_token: str = field(default_factory=lambda: os.getenv("GRAPH_TOKEN", ""))
    site: str = field(default_factory=lambda: os.getenv("GRAPH_SITE_ID", "demo-city"))
    list_id: str = field(default_factory=lambda: os.getenv("GRAPH_LIST_ID", "service-requests"))

    def __post_init__(self):
        self.ollama_url = local_url(self.ollama_url)
        self.graph_url = local_url(self.graph_url)
        if ":" in self.model and self.model.endswith(":cloud"):
            raise ValueError("Use a local model")
