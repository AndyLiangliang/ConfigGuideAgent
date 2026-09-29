"""代码裁判。型号对错不交给模型。"""

from __future__ import annotations

import re
from pathlib import Path

from src.catalog import load_catalog, search_catalog, skus_of

ROOT = Path(__file__).resolve().parents[1]

# 离线期望。case3 缺预算，不进这张表。
EXPECTED = [
    {
        "id": "case1",
        "request": {
            "customer": "星海制造",
            "scene": "办公终端",
            "lines": ["PC"],
            "qty": {"PC": 10},
            "budget_tier": "中",
            "prefer": "default",
        },
        "standard": ["SYN-PC-02"],
        "hot": ["SYN-PC-03"],
        "forbidden": ["SYN-PC-04"],
    },
    {
        "id": "case2",
        "request": {
            "customer": "",
            "scene": "机房",
            "lines": ["Server", "Storage"],
            "qty": {"Server": 2, "Storage": 1},
            "budget_tier": "高",
            "prefer": "lead_time",
        },
        "standard": ["SYN-SV-02", "SYN-ST-02"],
        "hot": ["SYN-SV-04", "SYN-ST-04"],
        "forbidden": [],
    },
    {
        "id": "case4",
        "request": {
            "customer": "星海制造",
            "scene": "办公终端",
            "lines": ["PC"],
            "qty": {"PC": 10},
            "budget_tier": "高",
            "prefer": "default",
        },
        "standard": ["SYN-PC-02"],
        "hot": ["SYN-PC-04"],
        "forbidden": [],
    },
]


def check_catalog() -> list[str]:
    catalog = load_catalog()
    errors: list[str] = []
    for case in EXPECTED:
        result = search_catalog(catalog, case["request"])
        standard, hot = skus_of(result)
        if standard != case["standard"] or hot != case["hot"]:
            errors.append(
                f"{case['id']} 期望标准 {case['standard']} 热推 {case['hot']}，"
                f"实际标准 {standard} 热推 {hot}"
            )
        chosen = set(standard + hot)
        for sku in case["forbidden"]:
            if sku in chosen:
                errors.append(f"{case['id']} 不应出现 {sku}")
        for bucket in ("standard", "hot_plan"):
            for item in result[bucket]:
                if not item["menu_path"] or item["sku"] not in item["menu_path"][-1]:
                    errors.append(f"{item['sku']} 的 menu_path 最后一级未包含型号")
    return errors


SKU_PATTERN = re.compile(r"SYN-[A-Z]+-\d{2}")


def unique_skus(text: str) -> list[str]:
    found: list[str] = []
    for sku in SKU_PATTERN.findall(text or ""):
        if sku not in found:
            found.append(sku)
    return found


def tool_skus(request: dict) -> list[str]:
    standard, hot = skus_of(search_catalog(load_catalog(), request))
    return standard + hot


def expected_skus(case_id: str) -> tuple[list[str], list[str]]:
    case = next(item for item in EXPECTED if item["id"] == case_id)
    return case["standard"] + case["hot"], case["forbidden"]


def judge_body(case_id: str, request: dict | None, guide: str, a2a_calls: int) -> tuple[bool, str]:
    """返回是否一致，以及 eval.md 的一行。型号按集合比较，菜单路径里重复出现同一型号不算多一个。"""
    if case_id == "case3" or not request:
        body = unique_skus(guide)
        ok = body == [] and a2a_calls == 0
        mark = "是" if ok else "否"
        return ok, f"{case_id} |  |  |  | {mark}"
    tool = tool_skus(request)
    body = unique_skus(guide)
    expected, forbidden = expected_skus(case_id)
    ok = set(body) == set(tool) == set(expected) and not (set(forbidden) & set(body))
    mark = "是" if ok else "否"
    row = (
        f"{case_id} | {','.join(tool)} | {','.join(body)} | {','.join(expected)} | {mark}"
    )
    return ok, row


def check_static_sources() -> list[str]:
    """已存在的顾问、撰写、质检文件不得写死型号。顾问还必须注册工具。"""
    errors: list[str] = []
    advisor = ROOT / "src" / "advisor.py"
    if advisor.exists():
        text = advisor.read_text(encoding="utf-8")
        if "SYN-" in text:
            errors.append("advisor.py 含有 SYN- 字面量")
        if "add_tool(" not in text:
            errors.append("advisor.py 未调用 add_tool(")
    for name in ("writer_server.py", "reviewer_server.py"):
        path = ROOT / "src" / name
        if path.exists() and "SYN-" in path.read_text(encoding="utf-8"):
            errors.append(f"{name} 含有 SYN- 字面量")
    return errors
