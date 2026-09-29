"""ConfigGuideAgent 入口。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.advisor import build_advisor, called_catalog, parse_finish
from src.context_pack import build_context
from src.eval import EXPECTED, check_catalog, check_static_sources, judge_body
from src.memory_store import check_memory_roundtrip, recall_and_reprice, remember_request

RECALL_PATH = ROOT / "outputs" / "memory_recall.json"
EVAL_HEADER = "case_id | 工具返回 sku | 正文 sku | 期望 sku | 是否一致"
_SERVICES_STARTED = False
_A2A_CALLS = 0


def _recall_in_new_process() -> tuple[str, list[str]]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--memory-recall"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0 or not RECALL_PATH.exists():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(detail or "情景记忆检索进程没有写出结果")
    payload = json.loads(RECALL_PATH.read_text(encoding="utf-8"))
    return payload["text"], payload["hot"]


def run_check_only() -> int:
    errors = check_catalog() + check_static_sources()
    errors.extend(check_memory_roundtrip(_recall_in_new_process))
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("PASS 目录筛选：case1 / case2 / case4 的期望型号一致")
    print("PASS 情景记忆：新进程取回星海制造，预算改为高后热推是 SYN-PC-04")
    if (ROOT / "src" / "advisor.py").exists():
        print("PASS 静态检查：advisor.py 已注册工具且未写死型号")
    return 0


def load_case(case_id: str) -> str:
    cases = json.loads((ROOT / "data" / "cases.json").read_text(encoding="utf-8"))
    for case in cases:
        if case["id"] == case_id:
            return case["text"]
    raise KeyError(case_id)


def _wait_health(url: str) -> None:
    import requests

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            response = requests.get(f"{url}/health", timeout=2)
            if response.ok:
                return
        except requests.RequestException:
            time.sleep(0.3)
    raise RuntimeError(f"{url} 没有在 20 秒内就绪")


def ensure_services() -> None:
    global _SERVICES_STARTED
    if _SERVICES_STARTED:
        return
    from src.reviewer_server import serve as serve_reviewer
    from src.writer_server import serve as serve_writer

    threading.Thread(target=serve_writer, name="writer-a2a", daemon=True).start()
    threading.Thread(target=serve_reviewer, name="reviewer-a2a", daemon=True).start()
    _wait_health("http://127.0.0.1:5001")
    _wait_health("http://127.0.0.1:5002")
    _SERVICES_STARTED = True


def ask_a2a(url: str, name: str, question: str) -> str:
    """经 A2ATool 提问。库里的客户端把等待时间写死为 30 秒，规划执行和反思都超时，这里只把等待放宽。"""
    global _A2A_CALLS
    import hello_agents.protocols.a2a.implementation as impl
    from hello_agents.tools import A2ATool

    original = impl.A2AClient.ask

    def ask(self, question: str) -> str:
        import requests

        response = requests.post(
            f"{self.server_url}/ask",
            json={"question": question},
            timeout=240,
        )
        response.raise_for_status()
        return response.json().get("answer", "No response")

    impl.A2AClient.ask = ask
    try:
        tool = A2ATool(agent_url=url, name=name)
        raw = tool.run({"action": "ask", "question": question})
    finally:
        impl.A2AClient.ask = original
    _A2A_CALLS += 1
    prefix = "Agent 回答:\n"
    if raw.startswith(prefix):
        return raw[len(prefix) :]
    return raw


def write_and_review(case_id: str, user_text: str, payload: dict) -> tuple[int, str]:
    request = payload["request"]
    packet = build_context(user_text, request)
    ensure_services()
    draft = ask_a2a("http://127.0.0.1:5001", "write_guide", packet)
    if not draft or draft.startswith("No suitable") or "无法生成有效的行动计划" in draft:
        print(f"FAIL {case_id} 撰写没有产出指引: {draft}")
        return 1, ""
    reviewed = ask_a2a(
        "http://127.0.0.1:5002",
        "review_guide",
        f"上下文包：\n{packet}\n\n草稿：\n{draft}",
    )
    guide = reviewed or draft
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / f"{case_id}_guide.md").write_text(guide, encoding="utf-8")
    ok, row = judge_body(case_id, request, guide, _A2A_CALLS)
    print(row)
    if not ok:
        print(f"FAIL {case_id} 正文型号与工具返回不一致")
        return 1, row
    customer = payload.get("customer") or request.get("customer") or ""
    if customer:
        remember_request(customer, request)
    print(f"PASS {case_id} 指引已通过代码判定")
    return 0, row


def run_case(case_id: str) -> tuple[int, str]:
    advisor = build_advisor()
    answer = advisor.run(load_case(case_id), temperature=0)
    try:
        payload = parse_finish(answer)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL {case_id} 无法解析 Finish: {exc}")
        return 1, ""
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / f"{case_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    used_catalog = called_catalog(advisor)
    calls_before = _A2A_CALLS
    if case_id == "case3":
        if payload.get("need_clarify") is not True or used_catalog:
            print(f"FAIL case3 应追问且不查目录，实际 {payload} catalog={used_catalog}")
            return 1, ""
        ok, row = judge_body(case_id, None, "", _A2A_CALLS - calls_before)
        print("PASS case3：缺预算，已追问，未查目录")
        print(row)
        return (0, row) if ok else (1, row)
    expected = next(item for item in EXPECTED if item["id"] == case_id)
    if payload.get("need_clarify"):
        print(f"FAIL {case_id} 不应追问: {payload.get('clarify')}")
        return 1, ""
    if not used_catalog:
        print(f"FAIL {case_id} 没有调用目录工具")
        return 1, ""
    request = payload.get("request") or {}
    if not isinstance(request.get("qty"), dict):
        print(f"FAIL {case_id} 的 qty 必须是按产品线的对象，实际 {request.get('qty')}")
        return 1, ""
    if payload.get("standard_sku") != expected["standard"] or payload.get("hot_sku") != expected["hot"]:
        print(
            f"FAIL {case_id} 型号不符，期望标准 {expected['standard']} 热推 {expected['hot']}，"
            f"实际标准 {payload.get('standard_sku')} 热推 {payload.get('hot_sku')}"
        )
        return 1, ""
    print(f"PASS {case_id}：标准 {payload['standard_sku']} 热推 {payload['hot_sku']}，已查目录")
    return write_and_review(case_id, load_case(case_id), payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="教学用 ToB 配单点击指引")
    parser.add_argument("--check-only", action="store_true", help="只跑离线断言")
    parser.add_argument("--case", default="", help="只跑指定用例")
    parser.add_argument("--memory-recall", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.memory_recall:
        text, hot = recall_and_reprice()
        RECALL_PATH.write_text(
            json.dumps({"text": text, "hot": hot}, ensure_ascii=False),
            encoding="utf-8",
        )
        return 0
    if args.case:
        code, _row = run_case(args.case)
        return code
    if args.check_only:
        return run_check_only()
    rows = [EVAL_HEADER]
    code = 0
    for case_id in ("case1", "case2", "case3", "case4"):
        case_code, row = run_case(case_id)
        if row:
            rows.append(row)
        if case_code:
            code = 1
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / "eval.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
