"""读取 Qdrant、嵌入和对话模型配置。密钥只留在 .env，不写进源码。"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
REPO_ENV = REPO_ROOT / ".env"

KEEP_KEYS = (
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_DISTANCE",
    "QDRANT_TIMEOUT",
    "EMBED_MODEL_TYPE",
    "EMBED_MODEL_NAME",
    "EMBED_API_KEY",
    "EMBED_BASE_URL",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL_ID",
    "LLM_TIMEOUT",
)

COLLECTION = "configguide_episodic"


def _env_files() -> list[Path]:
    """先读仓库根目录，再用本目录里的非空值覆盖。单独克隆时只需要本目录的 .env。"""
    local = ROOT / ".env"
    files = []
    for path in (REPO_ENV, local):
        if path.exists() and path not in files:
            files.append(path)
    return files


def load_root_qdrant_env() -> None:
    files = _env_files()
    if not files:
        raise FileNotFoundError(
            "找不到环境文件。请把 .env.example 复制为 "
            f"{ROOT / '.env'} 并填写，或放在 {REPO_ENV}"
        )
    found = set()
    for env_file in files:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, value = text.split("=", 1)
            key = key.strip()
            if key not in KEEP_KEYS:
                continue
            cleaned = value.strip().strip('"').strip("'")
            if not cleaned:
                continue
            os.environ[key] = cleaned
            found.add(key)
    missing = [
        key
        for key in ("QDRANT_URL", "QDRANT_API_KEY", "EMBED_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_ID")
        if key not in found
    ]
    if missing:
        raise RuntimeError(".env 缺少: " + ", ".join(missing))
    os.environ["QDRANT_COLLECTION"] = COLLECTION
