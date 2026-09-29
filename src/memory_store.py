"""情景记忆往返。向量走仓库根目录的 Qdrant 云集群，原文落本地 SQLite。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from hello_agents.memory import MemoryConfig
from hello_agents.tools import MemoryTool

from src.catalog import load_catalog, search_catalog, skus_of
from src.root_env import COLLECTION, load_root_qdrant_env

ROOT = Path(__file__).resolve().parents[1]
MEMORY_DIR = ROOT / "memory_data"
CASE1_REQUEST = {
    "customer": "星海制造",
    "scene": "办公终端",
    "lines": ["PC"],
    "qty": {"PC": 10},
    "budget_tier": "中",
    "prefer": "default",
}


def _tool() -> MemoryTool:
    load_root_qdrant_env()
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    config = MemoryConfig(storage_path=str(MEMORY_DIR))
    return MemoryTool(
        user_id="sales_demo",
        memory_config=config,
        memory_types=["working", "episodic"],
    )


def remember_case1() -> str:
    tool = _tool()
    content = json.dumps(
        {"customer": "星海制造", "request": CASE1_REQUEST},
        ensure_ascii=False,
    )
    return tool.run(
        {
            "action": "add",
            "content": content,
            "memory_type": "episodic",
            "importance": 0.9,
        }
    )


def _sqlite_hit() -> str:
    db_path = MEMORY_DIR / "memory.db"
    if not db_path.exists():
        return ""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT content FROM memories WHERE content LIKE ?",
            ("%星海制造%",),
        ).fetchall()
    return rows[-1][0] if rows else ""


def full_episode(customer: str) -> str:
    """MemoryTool 的搜索展示会截断 JSON。配单要读完整 request 时用原文。"""
    if not customer:
        return ""
    db_path = MEMORY_DIR / "memory.db"
    if not db_path.exists():
        return ""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT content FROM memories WHERE content LIKE ? ORDER BY rowid",
            (f"%{customer}%",),
        ).fetchall()
    return rows[-1][0] if rows else ""


def search_episodic(customer: str) -> str:
    if not customer:
        return ""
    tool = _tool()
    text = tool.run(
        {
            "action": "search",
            "query": customer,
            "memory_type": "episodic",
            "limit": 3,
        }
    )
    if customer not in text or "[..." in text:
        text = full_episode(customer) or text
    return text


def remember_request(customer: str, request: dict) -> str:
    if not customer:
        return ""
    tool = _tool()
    content = json.dumps(
        {"customer": customer, "request": request},
        ensure_ascii=False,
    )
    return tool.run(
        {
            "action": "add",
            "content": content,
            "memory_type": "episodic",
            "importance": 0.9,
        }
    )


def recall_xinghai() -> str:
    tool = _tool()
    text = tool.run(
        {
            "action": "search",
            "query": "星海制造",
            "memory_type": "episodic",
            "limit": 3,
        }
    )
    if "星海制造" not in text:
        text = _sqlite_hit()
    return text


def recall_and_reprice() -> tuple[str, list[str]]:
    text = recall_xinghai()
    raw = _sqlite_hit()
    if "星海制造" not in text or "星海制造" not in raw:
        raise RuntimeError("新进程没有取回星海制造的情景记忆")
    payload = json.loads(raw)
    request = dict(payload["request"])
    request["budget_tier"] = "高"
    _, hot = skus_of(search_catalog(load_catalog(), request))
    return text, hot


def check_memory_roundtrip(recall_fn) -> list[str]:
    """recall_fn 必须在新进程里调用 recall_and_reprice。"""
    errors: list[str] = []
    try:
        remember_case1()
        text, hot = recall_fn()
    except Exception as exc:
        return [f"情景记忆失败（集合 {COLLECTION}）: {exc}"]
    if "星海制造" not in text:
        errors.append("情景记忆检索结果不含星海制造")
    if hot != ["SYN-PC-04"]:
        errors.append(f"预算改为高后热推应为 SYN-PC-04，实际 {hot}")
    return errors
