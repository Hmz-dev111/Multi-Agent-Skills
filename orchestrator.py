# orchestrator.py
"""
Orchestrator：技能感知的主控调度器

核心逻辑：
1. 启动时扫描 skills/ 目录，加载所有技能元数据，构建技能目录
2. 将技能目录注入自身 system prompt，让 LLM 知道有哪些能力可调用
3. 用户输入后，LLM 判断是否触发 CVRPTW 相关技能：
   - 是 → 解析 instance → 并行 solve+retrieve → validate → report
   - 否 → 直接用 LLM 回答，不调用任何 Agent
4. 持续交互，输入 quit 退出
"""
import os
import json
import asyncio
import re
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from openai import OpenAI
import yaml

load_dotenv()

from agents.base_agent import discover_skills, build_skills_catalog, extract_json
from agents.solver_validator_agent import SolverValidatorAgent
from agents.knowledge_agent        import KnowledgeAgent

KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
MODEL         = "kimi-k2.5"
OUTPUT_DIR    = os.path.join(os.path.dirname(__file__), "output")


# ── Orchestrator System Prompt 模板 ───────────────────────────────────────────
ORCHESTRATOR_SYSTEM_TEMPLATE = """\
你是一个智能任务调度助手，能够直接回答一般问题，也能识别并调度专业技能来处理特定任务。

{skills_catalog}

---

## 调度协议（必须严格遵守）

当你决定调用某个技能时，**只输出 JSON**，格式如下：

```json
{{
  "action": "dispatch_skill",
  "skill": "<skill_name>",
  "reason": "<简短原因>",
  "payload": {{ ... }}
}}
```

其中 payload 的结构由技能元数据决定：每个技能都在 catalog 中提供了 input_key 与 schema_paths。

{dispatch_instructions}

---

## 直接回答
若用户只是咨询/讨论/提问（不需要运行技能），则直接用自然语言回答，**不要输出 JSON**。

## 重要
- dispatch_skill 时：**只输出 JSON**
- 直接回答时：**只输出自然语言**
"""


def _safe_read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_schema(path: str) -> Dict[str, Any]:
    """Load yaml/json schema file."""
    text = _safe_read_text(path)
    if path.lower().endswith((".yaml", ".yml")):
        return yaml.safe_load(text) or {}
    return json.loads(text)


def _example_from_schema(schema: Dict[str, Any]) -> Any:
    """Generate a minimal example object from a (JSONSchema-like) schema."""
    if not isinstance(schema, dict):
        return {}
    t = schema.get("type")

    if t == "object":
        props = schema.get("properties") or {}
        req = schema.get("required") or []
        out: Dict[str, Any] = {}
        for k in req:
            out[k] = _example_from_schema(props.get(k, {}))
        if not out and props:
            k0 = next(iter(props.keys()))
            out[k0] = _example_from_schema(props.get(k0, {}))
        return out

    if t == "array":
        items = schema.get("items") or {}
        return [_example_from_schema(items)]

    if t == "integer":
        return 0
    if t == "number":
        return 0
    if t == "boolean":
        return False

    return ""


def build_dispatch_instructions(skills: Dict[str, Dict[str, Any]]) -> str:
    """Generate per-skill dispatch templates from SKILL.md frontmatter schema_paths."""
    blocks = []
    for name, meta in skills.items():
        input_key = meta.get("input_key") or "input"
        schema_paths = meta.get("schema_paths") or {}
        skill_dir = meta.get("_dir") or os.path.join(os.path.dirname(__file__), "skills", name)

        example_payload: Dict[str, Any]
        if schema_paths.get("input"):
            schema_file = schema_paths["input"]
            schema_path = schema_file if os.path.isabs(schema_file) else os.path.join(skill_dir, schema_file)
            try:
                schema = _load_schema(schema_path)
                example_payload = _example_from_schema(schema)
            except Exception:
                example_payload = {input_key: ""}
        else:
            example_payload = {input_key: ""}

        blocks.append(
            "### " + name + "\n"
            "当需要调用该技能时，payload 至少应包含 key: `" + input_key + "`。示例：\n\n"
            "```json\n"
            + json.dumps(
                {
                    "action": "dispatch_skill",
                    "skill": name,
                    "reason": "...",
                    "payload": example_payload,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n```\n"
        )
    return "\n".join(blocks)


class Orchestrator:

    def __init__(self):
        if not KIMI_API_KEY:
            raise ValueError("KIMI_API_KEY 未设置，请在 .env 中配置")

        # 启动时：扫描 skills/*/SKILL.md frontmatter，构建技能目录（渐进式披露第一层）
        self.skills = discover_skills()
        skills_catalog_text = build_skills_catalog(self.skills)
        dispatch_instructions = build_dispatch_instructions(self.skills)
        self.system_prompt = ORCHESTRATOR_SYSTEM_TEMPLATE.format(
            skills_catalog=skills_catalog_text,
            dispatch_instructions=dispatch_instructions,
        )

        # 初始化 Kimi 客户端（Orchestrator 自己用于路由判断）
        self.llm_client = OpenAI(api_key=KIMI_API_KEY, base_url=KIMI_BASE_URL)

        # 初始化两个 Agent
        self.solver_validator = SolverValidatorAgent(KIMI_API_KEY)
        self.knowledge        = KnowledgeAgent(KIMI_API_KEY, output_dir=OUTPUT_DIR)

        print("[Orchestrator] 初始化完成")
        print(f"  已加载技能: {list(self.skills.keys())}")
        print(f"  输出目录:   {OUTPUT_DIR}\n")

    # ── 路由判断 ──────────────────────────────────────────────────────────────
    def _route(self, user_input: str) -> Dict[str, Any]:
        """
        让 LLM 判断用户意图：
        返回 {"action": "dispatch_skill", "instance": {...}} 或 {"action": "direct_answer", "content": "..."}
        """
        response = self.llm_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user",   "content": user_input}
            ]
        )
        raw = response.choices[0].message.content or ""

        # 尝试解析为 dispatch 指令（新协议：payload + skill）
        parsed = extract_json(raw)
        if parsed and parsed.get("action") == "dispatch_skill":
            skill = parsed.get("skill")
            payload = parsed.get("payload")
            if isinstance(skill, str) and isinstance(payload, dict) and skill in self.skills:
                return {"action": "dispatch_skill", "skill": skill, "payload": payload, "reason": parsed.get("reason", "")}

        # 否则视为直接回答
        return {"action": "direct_answer", "content": raw}

    # ── 异步并行包装 ──────────────────────────────────────────────────────────
    async def _async_retrieve(self, instance):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.knowledge.retrieve_context, instance)

    # ── 技能执行流水线 ─────────────────────────────────────────────────────────
    async def _run_skill_pipeline(self, instance: Dict[str, Any]) -> Dict[str, Any]:
        n = len(instance.get("customers", []))
        print("=" * 62)
        print(f"[Orchestrator] 技能调度启动 | 客户数: {n} | 容量: {instance.get('capacity')}")
        print("=" * 62)

        # Step 1: KnowledgeAgent retrieve 并行（Solver 不再单独并行，改为 Step 2 统一循环）
        print("\n[Step 1] KnowledgeAgent(retrieve) 并行启动 ‖ SolverValidatorAgent 准备中...")
        retrieve_task = asyncio.create_task(self._async_retrieve(instance))

        # Step 2: solve→validate 循环（最多5轮），与 retrieve 并行执行
        loop = asyncio.get_event_loop()
        solve_validate_task = loop.run_in_executor(None, self.solver_validator.solve_and_validate, instance, 3)

        knowledge_result, validator_result = await asyncio.gather(retrieve_task, solve_validate_task)

        print(f"\n[Step 1+2 完成]")
        print(f"  Knowledge → 分类: {knowledge_result.get('instance_classification', 'N/A')}")
        print(f"              web_search 已使用: {knowledge_result.get('_web_search_used', False)}")
        print(f"  Solver    → 最终状态: {validator_result.get('status')} | "
              f"成本: {validator_result.get('original_cost')} → {validator_result.get('final_cost')} "
              f"(↓{validator_result.get('improvement_rate', 0)}%)")

        # solver_result 供报告使用（从 validator_result 中取出求解摘要）
        solver_result = {
            "solution":    validator_result.get("solution", []),
            "num_vehicles": validator_result.get("num_vehicles", 0),
            "reasoning":   validator_result.get("solver_reasoning", "")
        }

        # Step 3: report
        print("\n[Step 3] KnowledgeAgent(report) — 串行")
        report_result = self.knowledge.generate_report(
            instance=instance,
            solver_result=solver_result,
            validator_result=validator_result,
            knowledge=knowledge_result
        )

        return {
            "status":           "success",
            "feasible":         validator_result.get("status") in ("feasible", "improved"),
            "final_solution":   validator_result.get("solution", []),
            "num_vehicles":     len(validator_result.get("solution", [])),
            "original_cost":    validator_result.get("original_cost"),
            "final_cost":       validator_result.get("final_cost"),
            "improvement_rate": validator_result.get("improvement_rate", 0),
            "output_files":     {
                "json": report_result.get("json_path"),
                "docx": report_result.get("docx_path")
            }
        }

    # ── 主处理入口 ────────────────────────────────────────────────────────────
    def handle(self, user_input: str) -> None:
        print("\n[Orchestrator] 路由判断中...")

        # Fast path: explicit slash invocation: /skill_name <text>
        m = re.match(r"^\s*/([a-zA-Z0-9_\-]+)\s+(.*)$", user_input, re.DOTALL)
        if m and m.group(1) in self.skills:
            skill = m.group(1)
            rest = m.group(2).strip()
            route = {"action": "dispatch_skill", "skill": skill, "payload": {"question": rest, "query": rest, "instance": rest}, "reason": "slash_invoke"}
        else:
            route = self._route(user_input)

        if route["action"] == "direct_answer":
            # 非 CVRPTW 求解问题，直接输出 LLM 回答
            print("\n[Orchestrator] 直接回答（未触发技能调度）\n")
            print("─" * 62)
            print(route["content"])
            print("─" * 62)

        elif route["action"] == "dispatch_skill":
            skill = route.get("skill")
            payload = route.get("payload") or {}
            print(f"[Orchestrator] 触发技能调度 → {skill} | {route.get('reason', '')}")

            if skill == "solver_validator":
                instance = payload.get("instance") if isinstance(payload, dict) else None
                if not isinstance(instance, dict):
                    print("[ERROR] solver_validator 需要 payload.instance (dict)。")
                    return
                print(f"\n已解析实例：仓库={instance.get('depot')}，容量={instance.get('capacity')}，客户数={len(instance.get('customers', []))}")
                confirm = input("确认开始求解？(y/n，回车默认 y): ").strip().lower()
                if confirm == "n":
                    print("已取消。")
                    return
                result = asyncio.run(self._run_skill_pipeline(instance))

            elif skill == "knowledge_report":
                question = None
                if isinstance(payload, dict):
                    question = payload.get("question") or payload.get("query")
                if not isinstance(question, str) or not question.strip():
                    print("[ERROR] knowledge_report 需要 payload.question (string)。")
                    return
                answer = self.knowledge.answer_question(question.strip())
                print("\n[Orchestrator] knowledge_report 回答\n")
                print("─" * 62)
                print(answer.get("answer", ""))
                if answer.get("sources"):
                    print("\nSources:")
                    for s in answer["sources"]:
                        print("  -", s)
                print("─" * 62)
                return
            else:
                print(f"[ERROR] 未实现的 skill 执行入口: {skill}")
                return

            print("\n" + "=" * 62)
            print("[Orchestrator] 求解完成！")
            print(f"  可行性:   {result['feasible']}")
            print(f"  车辆数:   {result['num_vehicles']}")
            print(f"  原始成本: {result['original_cost']}")
            print(f"  优化成本: {result['final_cost']}  (↓{result['improvement_rate']}%)")
            print(f"  JSON:     {result['output_files']['json']}")
            print(f"  DOCX:     {result['output_files']['docx']}")
            print("=" * 62)


# ── 交互式命令行 ──────────────────────────────────────────────────────────────
def print_help():
    print("""
使用说明：
  · 直接提问（咨询）    → Orchestrator 直接回答，不调用 Agent
  · 提供 CVRPTW 实例   → 自动触发技能调度，启动 Multi-Agent 求解

提问示例（直接回答）：
  什么是 CVRPTW？
  2-opt 和 LNS 有什么区别？

求解示例（触发技能）：
  仓库在(0,0)，容量100，有3个客户：
  客户1在(10,20)，需求15，时间窗[0,100]，服务时间10
  客户2在(30,10)，需求25，时间窗[20,80]，服务时间10
  客户3在(20,30)，需求20，时间窗[50,150]，服务时间10

  或直接粘贴 JSON 格式的 instance 数据。

输入 help 查看此说明，quit 退出。
""")


def main():
    print("=" * 62)
    print("  CVRPTW Skills-Based Multi-Agent 系统")
    print("  Powered by Kimi + Skills + Two-Agent Pipeline")
    print("=" * 62)

    if not KIMI_API_KEY:
        print("[ERROR] 请在 .env 中设置 KIMI_API_KEY")
        return

    print_help()
    orchestrator = Orchestrator()

    while True:
        print()
        print("请输入（多行输入以空行结束）：")
        lines = []
        try:
            while True:
                line = input(">>> " if not lines else "... ")
                low  = line.strip().lower()
                if low in ("quit", "q", "exit"):
                    print("再见！")
                    return
                if low == "help":
                    print_help()
                    lines = []
                    break
                if line.strip() == "" and lines:
                    break
                if line.strip():
                    lines.append(line)
        except (KeyboardInterrupt, EOFError):
            print("\n再见！")
            return

        if not lines:
            continue

        orchestrator.handle("\n".join(lines))


if __name__ == "__main__":
    main()
