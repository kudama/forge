import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    database: Path
    principals: dict[str, dict]
    model_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:8b"
    timeout: float = 60
    context_length: int = 4096
    max_output_tokens: int = 512
    capacity: int = 8
    tool_rounds: int = 3
    repositories: dict[str, dict] = field(default_factory=dict)
    examples_file: Path | None = None
    role_models: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.role_models, dict) or any(
            role not in {'forge', 'repository_analyst', 'implementer'}
            or not isinstance(model, str) or not model or model.strip() != model
            for role, model in self.role_models.items()
        ):
            raise ValueError('Invalid role model mapping')
        if type(self.context_length) is not int or self.context_length <= 0:
            raise ValueError("context_length must be a positive integer")
        if type(self.max_output_tokens) is not int or self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be a positive integer")
        url = urlparse(self.model_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Invalid model URL")
        if self.timeout <= 0 or self.capacity < 1 or self.tool_rounds < 1:
            raise ValueError("Limits must be positive")
        if not self.model or not self.principals:
            raise ValueError("Model and principals are required")
        tokens = []
        for name, grants in self.principals.items():
            if not name or not isinstance(grants, dict) or set(grants) not in ({'token', 'agents', 'services'}, {'token', 'agents', 'services', 'repositories'}):
                raise ValueError("Invalid principal")
            token = grants.get("token", "")
            if not isinstance(token, str) or len(token) < 32:
                raise ValueError("Tokens must contain at least 32 characters")
            if not isinstance(grants.get("agents"), list) or not grants["agents"] or any(a not in {"forge", "repository_analyst", "implementer"} for a in grants["agents"]):
                raise ValueError("Unknown or missing agent grant")
            services = grants.get("services", [])
            if not isinstance(services, list) or any(s != "prototype" for s in services):
                raise ValueError("Only the synthetic prototype service is supported")
            repositories = grants.get('repositories', [])
            if not isinstance(repositories, list) or any(not isinstance(r, str) or r not in self.repositories for r in repositories):
                raise ValueError('Invalid repository grant')
            tokens.append(token)
        if len(set(tokens)) != len(tokens):
            raise ValueError("Principal tokens must be unique")

        for name, repo in self.repositories.items():
            if not isinstance(repo, dict) or set(repo) != {'root', 'files'}:
                raise ValueError('Invalid repository manifest')
            root = Path(repo['root'])
            if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.resolve() != root:
                raise ValueError('Repository root must be canonical and absolute')
            if not isinstance(repo['files'], list) or not repo['files'] or len(repo['files']) > 100:
                raise ValueError('Repository manifest must list 1–100 approved files')
            for file in repo['files']:
                if not isinstance(file, str):
                    raise ValueError('Invalid source path')
                path = Path(file)
                if path.is_absolute() or path.as_posix() != file or any(p.startswith('.') for p in path.parts) or path.suffix not in {'.py', '.md', '.toml'}:
                    raise ValueError('Only explicit non-hidden source paths are allowed')

    def model_for(self, agent):
        if agent not in {'forge', 'repository_analyst', 'implementer'}:
            raise ValueError('Unknown agent')
        return self.role_models.get(agent, self.model)

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
            role_models=json.loads(os.environ.get("FORGE_ROLE_MODELS", "{}")),
            context_length=int(os.environ.get("FORGE_CONTEXT_LENGTH", "4096")),
            max_output_tokens=int(os.environ.get("FORGE_MAX_OUTPUT_TOKENS", "512")),
            timeout=float(os.environ.get("FORGE_TASK_TIMEOUT", "60")),
            capacity=int(os.environ.get("FORGE_CAPACITY", "8")),
            tool_rounds=int(os.environ.get("FORGE_TOOL_ROUNDS", "3")),
            examples_file=Path(os.environ["FORGE_EXAMPLES_FILE"]).expanduser() if os.environ.get("FORGE_EXAMPLES_FILE") else None,
            repositories=json.loads(Path(os.environ["FORGE_REPOSITORIES_FILE"]).read_text()) if os.environ.get("FORGE_REPOSITORIES_FILE") else {},
        )
