import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    database: Path
    principals: dict[str, dict]
    model_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:8b"
    timeout: float = 60
    capacity: int = 8
    tool_rounds: int = 3

    def __post_init__(self):
        url = urlparse(self.model_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Invalid model URL")
        if self.timeout <= 0 or self.capacity < 1 or self.tool_rounds < 1:
            raise ValueError("Limits must be positive")
        if not self.model or not self.principals:
            raise ValueError("Model and principals are required")
        tokens = []
        for name, grants in self.principals.items():
            if not name or not isinstance(grants, dict) or set(grants) != {'token', 'agents', 'services'}:
                raise ValueError("Invalid principal")
            token = grants.get("token", "")
            if not isinstance(token, str) or len(token) < 32:
                raise ValueError("Tokens must contain at least 32 characters")
            if grants.get("agents") != ["forge"]:
                raise ValueError("This prototype only supports agent forge")
            services = grants.get("services", [])
            if not isinstance(services, list) or any(s != "prototype" for s in services):
                raise ValueError("Only the synthetic prototype service is supported")
            tokens.append(token)
        if len(set(tokens)) != len(tokens):
            raise ValueError("Principal tokens must be unique")

    @classmethod
    def from_environment(cls):
        path = Path(os.environ["FORGE_PRINCIPALS_FILE"]).expanduser()
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode) or mode & 0o077:
            raise ValueError("Principal file must be an owner-only regular file (mode 600)")
        return cls(
            database=Path(os.environ.get("FORGE_DATABASE", "state/tasks.sqlite3")).expanduser(),
            principals=json.loads(path.read_text()),
            model_url=os.environ.get("FORGE_MODEL_URL", "http://127.0.0.1:11434"),
            model=os.environ.get("FORGE_MODEL", "qwen3:8b"),
            timeout=float(os.environ.get("FORGE_TASK_TIMEOUT", "60")),
            capacity=int(os.environ.get("FORGE_CAPACITY", "8")),
            tool_rounds=int(os.environ.get("FORGE_TOOL_ROUNDS", "3")),
        )
