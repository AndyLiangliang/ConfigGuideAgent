"""Host 用 ContextBuilder 打上下文包。目录只放本次查询结果。"""

from __future__ import annotations

import json

from hello_agents.context.builder import ContextBuilder, ContextConfig, ContextPacket

from src.catalog import search_catalog_json
from src.memory_store import search_episodic

SYSTEM = (
    "用简体中文写点击指引。先写标准方案，再写热推方案。"
    "每条点击步骤照抄记录里的 menu_path，不要改写菜单名称。"
    "解释只用记录里的 spec、budget_tier、hot、margin_tier、lead_time_days。"
    "不要写入上下文里没有出现的型号。"
)


def build_context(user_text: str, request: dict) -> str:
    catalog_json = search_catalog_json(json.dumps(request, ensure_ascii=False))
    customer = request.get("customer") or ""
    memory_text = search_episodic(customer) if customer else ""
    if not memory_text:
        memory_text = "没有这位客户的情景记忆。"
    tool_text = catalog_json + "\n" + json.dumps(request, ensure_ascii=False)
    packets = [
        ContextPacket(
            content=memory_text,
            metadata={"type": "related_memory"},
        ),
        ContextPacket(
            content=tool_text,
            metadata={"type": "tool_result"},
        ),
    ]
    builder = ContextBuilder(
        memory_tool=None,
        rag_tool=None,
        config=ContextConfig(max_tokens=2000, min_relevance=0.0),
    )
    return builder.build(
        user_query=user_text,
        system_instructions=SYSTEM,
        additional_packets=packets,
    )
