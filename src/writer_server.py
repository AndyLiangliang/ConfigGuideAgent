"""A2A 撰写服务。规划三步后写出点击指引，再把结论存成笔记。"""

from __future__ import annotations

import json
from pathlib import Path

from hello_agents import HelloAgentsLLM, PlanAndSolveAgent
from hello_agents.protocols import A2AServer
from hello_agents.tools import NoteTool

from src.root_env import load_root_qdrant_env

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "notes"

PLANNER = """你是点击指引的规划器。把任务拆成恰好三个步骤，输出一个 Python 列表，并且必须放在 python 代码块里。
三个步骤固定为：
1. 写出标准方案的点击步骤，逐步照抄上下文中的 menu_path
2. 写出热推方案的点击步骤，逐步照抄上下文中的 menu_path
3. 汇总完整指引：原样保留前两步的点击步骤和型号，先标准后热推，并说明相对上次需求改了什么

任务: {question}

请严格按照以下格式输出：
```python
["写出标准方案的点击步骤，逐步照抄上下文中的 menu_path", "写出热推方案的点击步骤，逐步照抄上下文中的 menu_path", "汇总完整指引：原样保留前两步的点击步骤和型号，先标准后热推，并说明相对上次需求改了什么"]
```
"""

EXECUTOR = """你是点击指引的执行者。只输出当前步骤的正文，使用简体中文。
型号和点击路径只能照抄原始问题里已经出现的 sku 和 menu_path。
如果当前步骤包含「汇总」，必须把历史步骤里的标准方案和热推方案原样保留，先标准后热推，不能只写变化说明。
解释只用 spec、budget_tier、hot、margin_tier、lead_time_days。

# 原始问题:
{question}

# 完整计划:
{plan}

# 历史步骤与结果:
{history}

# 当前步骤:
{current_step}

请仅输出针对当前步骤的回答：
"""

server = A2AServer(
    name="writer",
    description="根据上下文包撰写点击指引",
    version="1.0.0",
)


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _find_object(text: str, required: set[str]) -> dict | None:
    decoder = json.JSONDecoder()
    index = 0
    found = None
    while index < len(text):
        start = text.find("{", index)
        if start < 0:
            break
        try:
            obj, length = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        index = start + max(length, 1)
        for item in _walk(obj):
            if required <= set(item):
                found = item
    return found


def conclusion_text(packet: str) -> str:
    request = _find_object(packet, {"lines", "budget_tier", "prefer"}) or {}
    catalog = _find_object(packet, {"standard", "hot_plan"}) or {}
    standard = [item.get("sku", "") for item in catalog.get("standard", []) if isinstance(item, dict)]
    hot = [item.get("sku", "") for item in catalog.get("hot_plan", []) if isinstance(item, dict)]
    customer = request.get("customer") or ""
    budget = request.get("budget_tier") or ""
    return f"客户：{customer}\n标准方案：{standard}\n热推方案：{hot}\n预算档：{budget}"


def _agent() -> PlanAndSolveAgent:
    load_root_qdrant_env()
    llm = HelloAgentsLLM(temperature=0)
    return PlanAndSolveAgent(
        name="指引撰写",
        llm=llm,
        custom_prompts={"planner": PLANNER, "executor": EXECUTOR},
    )


@server.skill("write_guide")
def write_guide(text: str) -> str:
    draft = _agent().run(text, temperature=0)
    notes = NoteTool(workspace=str(NOTES))
    notes.run(
        {
            "action": "create",
            "title": "配单结论",
            "content": conclusion_text(text),
            "note_type": "conclusion",
        }
    )
    return draft


def serve() -> None:
    server.run(host="127.0.0.1", port=5001)
