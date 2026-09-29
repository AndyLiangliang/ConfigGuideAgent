"""目录 MCP 服务。顾问只能通过这个工具看见 SKU。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hello_agents.protocols.mcp.server import MCPServer

from src.catalog import search_catalog_json


def search_catalog(input: str) -> str:
    """按产品线、预算档和偏好返回标准方案与热推方案。

    Args:
        input: request JSON 字符串，含 lines、budget_tier、prefer。
    """
    return search_catalog_json(input)


def main() -> None:
    server = MCPServer(name="catalog", description="教学配单目录")
    server.add_tool(
        search_catalog,
        name="search_catalog",
        description="按产品线、预算档和偏好返回标准方案与热推方案。参数是 request JSON 字符串。",
    )
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
