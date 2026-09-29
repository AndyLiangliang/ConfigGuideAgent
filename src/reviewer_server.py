"""A2A 质检服务。只对照上下文包改稿，不再查目录。"""

from __future__ import annotations

from hello_agents import HelloAgentsLLM, ReflectionAgent
from hello_agents.protocols import A2AServer

from src.root_env import load_root_qdrant_env

INITIAL = """任务里包含上下文包和草稿。请输出一份完整的简体中文点击指引。
先写标准方案，再写热推方案。点击步骤照抄上下文包里的 menu_path。
只保留上下文包里出现过的型号。草稿里已经写对的点击步骤请原样保留。

任务: {task}
"""

REFLECT = """只检查三件事，不要评价文采：
1. 正文里的型号是否都出现在上下文包里
2. 点击步骤是否照抄了 menu_path
3. 有没有写进没被选中的型号

# 原始任务:
{task}

# 当前回答:
{content}

如果这三件都没有问题，回答里必须包含「无需改进」。
否则只指出要删除或补回的句子。
"""

REFINE = """按反馈改稿。上下文包里被选中的型号和 menu_path 必须保留，不要新增型号。
先写标准方案，再写热推方案。

# 原始任务:
{task}

# 上一轮回答:
{last_attempt}

# 反馈意见:
{feedback}
"""

server = A2AServer(
    name="reviewer",
    description="对照上下文包检查点击指引",
    version="1.0.0",
)


def _agent() -> ReflectionAgent:
    load_root_qdrant_env()
    llm = HelloAgentsLLM(temperature=0)
    return ReflectionAgent(
        name="质检",
        llm=llm,
        max_iterations=2,
        custom_prompts={"initial": INITIAL, "reflect": REFLECT, "refine": REFINE},
    )


@server.skill("review_guide")
def review_guide(text: str) -> str:
    return _agent().run(text, temperature=0)


def serve() -> None:
    server.run(host="127.0.0.1", port=5002)
