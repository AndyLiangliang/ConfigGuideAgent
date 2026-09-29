"""配单顾问。目录经 MCP 查询，客户需求经记忆工具读写。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hello_agents import HelloAgentsLLM, ReActAgent
from hello_agents.memory import MemoryConfig
from hello_agents.tools import MCPTool, MemoryTool
from hello_agents.tools.base import Tool, ToolParameter

from src.memory_store import full_episode
from src.root_env import load_root_qdrant_env

ROOT = Path(__file__).resolve().parents[1]
CATALOG_SERVER = ROOT / "src" / "catalog_mcp.py"

PROMPT = """你是配单顾问。你可以通过思考分析问题，然后调用合适的工具，最后给出 JSON。

## 可用工具
{tools}

## 工作流程
每次回应只能有一个步骤，且必须包含 Thought 和 Action：

Thought: 分析还缺什么信息。
Action: 调用工具或结束。格式为：
- `工具名[参数]`
- `Finish[JSON]`

## 约束
- 预算、产品线、数量缺一不可。缺了就 Finish 追问，不要查目录。
- 用户提到上次、跟上次一样，或其他不要变时，先用 memory 检索该客户。只改用户点名的字段，其余字段照记忆里的 request 抄，然后必须重新查目录。记忆里没有这个客户，就 Finish 追问没有这位客户的最近配单，不要查目录。
- 型号只能来自目录工具的返回，不能凭记忆编造型号。
- memory 的参数是 JSON 字符串，例如 {{"action":"search","query":"客户名","memory_type":"episodic","limit":3}}。
- 目录工具的参数是 request JSON 字符串，字段为 customer、scene、lines、qty、budget_tier、prefer。lines 只能是 PC、Server、Storage、Switch。budget_tier 只能是低、中、高。prefer 只能是 default 或 lead_time。中等写成中。货期优先写成 lead_time。台式机和办公电脑写成 PC。服务器写成 Server，存储写成 Storage。没有点名客户时 customer 为空字符串。
- Finish 的 JSON 字段固定为 customer、request、standard_sku、hot_sku、need_clarify、clarify。缺槽时 need_clarify 为 true，clarify 是追问的一句话，standard_sku 和 hot_sku 为空数组，request 为 null。槽位齐全时 need_clarify 为 false，clarify 为 ""，standard_sku 与 hot_sku 从目录返回的 standard、hot_plan 里抄 sku，顺序与 lines 一致。request 必须包含 customer、scene、lines、qty、budget_tier、prefer。qty 是按产品线的对象，不能写成单个数字。

## 当前任务
**Question:** {question}

## 执行历史
{history}

现在开始你的推理和行动："""


class MemoryBridge(Tool):
    """把 ReAct 的字符串参数转成 MemoryTool 需要的 action。"""

    def __init__(self, inner: MemoryTool):
        super().__init__(
            name="memory",
            description=(
                "存储和检索客户需求。参数是 JSON 字符串，"
                "搜索示例："
                '{"action":"search","query":"客户名","memory_type":"episodic","limit":3}'
            ),
        )
        self.inner = inner

    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="input",
                type="string",
                description="JSON 字符串，含 action、query 或 content、memory_type",
                required=True,
            )
        ]

    def run(self, parameters: dict) -> str:
        raw = parameters.get("input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return "记忆参数不是 JSON。请传 action、query 或 content、memory_type。"
        if not isinstance(payload, dict) or "action" not in payload:
            return "记忆参数需要 action 字段。"
        result = self.inner.run(payload)
        query = str(payload.get("query") or "")
        if payload.get("action") == "search" and query and ("[..." in result or query not in result):
            full = full_episode(query)
            if full:
                return full
            if query not in result:
                return f"没有这位客户的最近配单：{query}"
        return result


def build_advisor() -> ReActAgent:
    load_root_qdrant_env()
    llm = HelloAgentsLLM(temperature=0)
    agent = ReActAgent(
        name="配单顾问",
        llm=llm,
        max_steps=6,
        custom_prompt=PROMPT,
    )
    catalog = MCPTool(
        name="catalog",
        server_command=[sys.executable, str(CATALOG_SERVER)],
    )
    expanded = catalog.get_expanded_tools()
    if not expanded:
        raise RuntimeError("目录 MCP 没有展开出 search_catalog")
    for tool in expanded:
        agent.tool_registry.register_tool(tool)
    memory = MemoryTool(
        user_id="sales_demo",
        memory_config=MemoryConfig(storage_path=str(ROOT / "memory_data")),
        memory_types=["working", "episodic"],
    )
    agent.add_tool(MemoryBridge(memory))
    return agent


def parse_finish(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"顾问没有返回 JSON: {text}")
    return json.loads(text[start : end + 1])


def called_catalog(agent: ReActAgent) -> bool:
    history = "\n".join(agent.current_history)
    return "search_catalog" in history
