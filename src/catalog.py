"""合成目录的筛选。型号只从这份数据里出。"""

from __future__ import annotations

import json
from pathlib import Path

TIER_RANK = {"低": 0, "中": 1, "高": 2}

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "catalog.json"


def load_catalog(path: Path | None = None) -> list[dict]:
    catalog_path = path or CATALOG_PATH
    with catalog_path.open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    if len(catalog) != 20:
        raise ValueError(f"目录必须是 20 条，实际 {len(catalog)} 条")
    return catalog


def search_catalog(catalog: list[dict], request: dict) -> dict:
    """按产品线返回标准方案和热推方案。数组顺序与 request['lines'] 一致。"""
    budget = TIER_RANK[request["budget_tier"]]
    prefer = request["prefer"]
    if prefer not in ("default", "lead_time"):
        raise ValueError(f"未知 prefer: {prefer}")

    standard: list[dict] = []
    hot_plan: list[dict] = []
    for line in request["lines"]:
        candidates = [
            item
            for item in catalog
            if item["line"] == line and TIER_RANK[item["budget_tier"]] <= budget
        ]
        plain = sorted(
            (item for item in candidates if not item["hot"]),
            key=lambda item: (item["lead_time_days"], item["sku"]),
        )
        hot = [item for item in candidates if item["hot"]]
        if prefer == "lead_time":
            hot.sort(key=lambda item: (item["lead_time_days"], item["sku"]))
        else:
            hot.sort(
                key=lambda item: (
                    -TIER_RANK[item["margin_tier"]],
                    item["lead_time_days"],
                    item["sku"],
                )
            )
        if not plain:
            raise ValueError(f"{line} 没有符合预算的标准方案")
        if not hot:
            raise ValueError(f"{line} 没有符合预算的热推方案")
        standard.append(plain[0])
        hot_plan.append(hot[0])
    return {"standard": standard, "hot_plan": hot_plan}


def search_catalog_json(request_json: str, catalog: list[dict] | None = None) -> str:
    request = json.loads(request_json)
    result = search_catalog(catalog if catalog is not None else load_catalog(), request)
    return json.dumps(result, ensure_ascii=False)


def skus_of(result: dict) -> tuple[list[str], list[str]]:
    return (
        [item["sku"] for item in result["standard"]],
        [item["sku"] for item in result["hot_plan"]],
    )
