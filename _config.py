"""Shared paths/config/state helpers for the publish-page skill.

Config and state live OUTSIDE the skill repo so secrets never get committed and
survive skill updates:

    ${CLAUDE_CONFIG_DIR:-~/.claude}/skill-data/publish-page/
        config.env   # S3 credentials + bucket/url, mode 600
        state.json   # { "onboarded": bool, "cloud_enabled": bool }

Override the config file location with $PUBLISH_PAGE_CONFIG.
"""

import json
import os
from pathlib import Path

SKILL_NAME = "publish-page"

REQUIRED = ("S3_BUCKET", "S3_PUBLIC_BASE", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
OPTIONAL = ("S3_ENDPOINT", "S3_REGION")


def data_dir() -> Path:
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    return base / "skill-data" / SKILL_NAME


def config_path() -> Path:
    override = os.environ.get("PUBLISH_PAGE_CONFIG")
    return Path(override) if override else data_dir() / "config.env"


def state_path() -> Path:
    return data_dir() / "state.json"


def _parse_env_file(path: Path) -> dict:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def load_config() -> dict:
    """S3_* config; environment variables override the config file."""
    file_cfg = _parse_env_file(config_path())
    return {k: (os.environ.get(k) or file_cfg.get(k, "")) for k in REQUIRED + OPTIONAL}


def missing_required(cfg: dict) -> list:
    return [k for k in REQUIRED if not cfg.get(k)]


def write_config(cfg: dict) -> Path:
    data_dir().mkdir(parents=True, exist_ok=True)
    path = config_path()
    lines = ["# publish-page config — written by setup.py. Do NOT commit this file.", ""]
    lines += [f"{k}={cfg.get(k, '')}" for k in REQUIRED + OPTIONAL]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def load_state() -> dict:
    path = state_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save_state(state: dict) -> Path:
    data_dir().mkdir(parents=True, exist_ok=True)
    path = state_path()
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return path
