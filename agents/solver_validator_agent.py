# # # agents/solver_validator_agent.py
# # import json
# # import sys
# # import os
# # sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# # from agents.base_agent import BaseAgent, extract_json
# # # 直接从 skill 文件夹内的 solver_validator.py 导入代码实现
# # from skills.solver_validator.solver_validator import (
# #     nearest_neighbor_solution,
# #     full_validation_report,
# #     improve_with_solver
# # )
# # from tools import parse_solution
# # from typing import Dict, Any, List

# # SOLVER_VALIDATOR_TOOLS = [
# #     {
# #         "type": "function",
# #         "function": {
# #             "name": "check_cvrptw_solution",
# #             "description": "对 CVRPTW 路线方案进行完整可行性检查，返回违约信息和每条路线统计",
# #             "parameters": {
# #                 "type": "object",
# #                 "properties": {
# #                     "solution_text": {"type": "string", "description": "嵌套列表格式，如 '[[1,2],[3,4]]'"},
# #                     "instance":      {"type": "object", "description": "CVRPTW 问题实例"}
# #                 },
# #                 "required": ["solution_text", "instance"]
# #             }
# #         }
# #     },
# #     {
# #         "type": "function",
# #         "function": {
# #             "name": "improve_cvrptw_solution",
# #             "description": "对通过可行性检查的方案进行 2-opt 优化，降低总行驶成本",
# #             "parameters": {
# #                 "type": "object",
# #                 "properties": {
# #                     "solution_text": {"type": "string"},
# #                     "instance":      {"type": "object"}
# #                 },
# #                 "required": ["solution_text", "instance"]
# #             }
# #         }
# #     }
# # ]


# # class SolverValidatorAgent(BaseAgent):

# #     def __init__(self, api_key: str):
# #         super().__init__(api_key, skill_name="solver_validator")
# #         self.tools = SOLVER_VALIDATOR_TOOLS
# #         self._current_instance = None

# #     def _handle_tool_call(self, name: str, args: Dict[str, Any]) -> str:
# #         solution_text = args.get("solution_text", "")
# #         instance      = args.get("instance", self._current_instance)
# #         solution      = parse_solution(solution_text)
# #         if isinstance(solution, str):
# #             return json.dumps({"error": f"解析失败: {solution}"}, ensure_ascii=False)
# #         if name == "check_cvrptw_solution":
# #             return json.dumps(full_validation_report(solution, instance), ensure_ascii=False, indent=2)
# #         if name == "improve_cvrptw_solution":
# #             return json.dumps(improve_with_solver(solution, instance), ensure_ascii=False, indent=2)
# #         return json.dumps({"error": f"未知工具: {name}"})

# #     # ── 内部：单次生成解 ──────────────────────────────────────────────────────
# #     def _generate_solution(self, instance: Dict[str, Any], feedback: str = "") -> Dict[str, Any]:
# #         """
# #         调用 LLM 生成一次初始解。
# #         feedback 非空时表示上一轮 validate 失败，将错误原因一并传入，
# #         让 Agent 自行决定是调用 skill（启发式）还是直接生成修正解。
# #         """
# #         if feedback:
# #             prompt = (
# #                 f"【重新生成解 — 上一轮验证失败】\n\n"
# #                 f"问题实例：\n```json\n{json.dumps(instance, ensure_ascii=False, indent=2)}\n```\n\n"
# #                 f"上一轮违约原因：\n{feedback}\n\n"
# #                 f"请分析上述错误，决定是调用启发式 skill 还是直接生成修正解，"
# #                 f"确保新方案避免这些违约。输出 Phase 1 JSON。"
# #             )
# #         else:
# #             prompt = f"【Phase 1 — 生成初始解】\n\n```json\n{json.dumps(instance, ensure_ascii=False, indent=2)}\n```"

# #         raw    = self.run(prompt)
# #         result = extract_json(raw)
# #         if result and "solution" in result:
# #             return result
# #         # LLM 解析失败 → 启发式 fallback
# #         fb = nearest_neighbor_solution(instance)
# #         fb["reasoning"] = "LLM 输出解析失败，自动使用最近邻启发式算法"
# #         return fb

# #     # ── 内部：单次验证 ────────────────────────────────────────────────────────
# #     def _run_validate(self, solution: List[List[int]], instance: Dict[str, Any], initial_cost: float) -> Dict[str, Any]:
# #         """对给定方案执行一次验证+优化，返回结构化结果"""
# #         quick = full_validation_report(solution, instance)
# #         raw   = self.run(
# #             f"【Phase 2 — 验证并优化】\n\n"
# #             f"实例：\n```json\n{json.dumps(instance, ensure_ascii=False)}\n```\n\n"
# #             f"方案：`{solution}`\n\n"
# #             f"初步检查：\n```json\n{json.dumps(quick, ensure_ascii=False)}\n```"
# #         )
# #         result = extract_json(raw)
# #         if result and "status" in result:
# #             result["original_cost"] = initial_cost
# #             if result.get("final_cost") and result.get("final_cost") < result["original_cost"] and "improvement_rate" not in result:
# #                 result["improvement_rate"] = round((initial_cost - result["final_cost"]) / initial_cost * 100, 1)
# #             return result
# #         # LLM 解析失败 → 本地工具直接计算
# #         improved   = improve_with_solver(solution, instance) if quick["feasible"] else None
# #         final_cost = improved["cost"] if improved else quick.get("cost", 9999)
# #         return {
# #             "phase":  "validate",
# #             "status": "improved" if (improved and final_cost < initial_cost)
# #                       else ("feasible" if quick["feasible"] else "infeasible"),
# #             "solution":         improved["improved_solution"] if improved else solution,
# #             "original_cost":    initial_cost,
# #             "final_cost":       final_cost,
# #             "improvement_rate": round((initial_cost - final_cost) / initial_cost * 100, 1) if initial_cost > 0 else 0,
# #             "violations":       quick.get("violations", []),
# #             "route_details":    quick.get("route_details", []),
# #             "analysis":         "本地工具直接计算（LLM 输出解析失败）"
# #         }

# #     # ── 公开接口：solve + validate 循环 ──────────────────────────────────────
# #     def solve_and_validate(self, instance: Dict[str, Any], max_rounds: int = 6) -> Dict[str, Any]:
# #         """
# #         solve → validate 循环，最多 max_rounds 轮：
# #           - validate 通过（feasible / improved）→ 立即返回
# #           - validate 失败 → 把违约原因反馈给 Agent，重新 solve
# #           - 达到上限 → 返回最后一次 validate 结果（可能 infeasible）
# #         无论最终结果如何，都会返回结果交给 KnowledgeAgent 生成报告。
# #         """
# #         self._current_instance = instance
# #         n = len(instance.get("customers", []))
# #         print(f"  [SolverValidatorAgent] 开始 solve→validate 循环，客户数: {n}，最大轮数: {max_rounds}")

# #         feedback     = ""          # 上一轮的违约原因
# #         last_result  = None
# #         initial_cost = None        # 第一次 validate 的基准成本（用于计算改进率）

# #         for round_i in range(1, max_rounds + 1):
# #             # ── Solve ──
# #             print(f"\n  [Round {round_i}/{max_rounds}] Solve...")
# #             solver_result = self._generate_solution(instance, feedback)
# #             solution      = solver_result.get("solution", [])
# #             print(f"  [Round {round_i}] 生成解: {len(solution)} 辆车  {solution}")

# #             # 记录第一轮的基准成本
# #             if initial_cost is None:
# #                 quick_check  = full_validation_report(solution, instance)
# #                 initial_cost = quick_check.get("cost", 9999)

# #             # ── Validate ──
# #             print(f"  [Round {round_i}/{max_rounds}] Validate...")
# #             val_result = self._run_validate(solution, instance, initial_cost)
# #             status     = val_result.get("status", "infeasible")
# #             violations = val_result.get("violations", [])
# #             print(f"  [Round {round_i}] 验证结果: {status}  cost={val_result.get('final_cost')}  violations={violations}")

# #             last_result = val_result
# #             # 标记本轮的求解信息，供报告使用
# #             last_result["solver_reasoning"] = solver_result.get("reasoning", "")
# #             last_result["num_vehicles"]      = len(solution)

# #             if status in ("feasible", "improved"):
# #                 print(f"  [SolverValidatorAgent] ✅ 第 {round_i} 轮通过，停止循环")
# #                 break

# #             # validate 失败：构造反馈文本，下一轮传给 Agent
# #             feedback = (
# #                 f"第 {round_i} 轮方案验证失败，违约信息：\n"
# #                 + "\n".join(f"  - {v}" for v in violations)
# #                 + f"\n请针对以上问题重新生成方案。"
# #             )
# #             if round_i == max_rounds:
# #                 print(f"  [SolverValidatorAgent] ⚠️  达到最大轮数 {max_rounds}，最终状态: {status}，继续输出报告")

# #         return last_result

# # agents/solver_validator_agent.py
# """
# SolverValidatorAgent：CVRPTW 求解与验证 Agent（tool-free / 文件系统直读模式）

# 架构变化（相对旧版）：
#   - 移除了 SOLVER_VALIDATOR_TOOLS 和 _handle_tool_call()
#   - 不再向 LLM 注册 function tools，LLM 只需输出结构化 JSON
#   - Phase 1（solve）：
#       LLM 输出 solve JSON；若声明 use_heuristic=true，系统直接调用启发式
#   - Phase 2（validate）：
#       ① 系统本地运行 full_validation_report() → 得到 Observation
#       ② 若可行，系统本地运行 improve_with_solver() → 得到优化 Observation
#       ③ 把 Observation 注入 prompt，让 LLM 输出最终 validate JSON
#       ④ 若 LLM 解析失败，系统直接用本地结果 fallback
#   - 自愈循环：validate 失败 → 结构化 feedback（time_window/capacity/coverage）
#       → 下轮 solve 时随 prompt 注入 → LLM 针对性修正

# 这种"LLM 决策 + 本地执行 + Observation 回注"模式即 SKILL.md 描述的
# "文件系统直读 + 本地执行"workflow，不依赖 OpenAI function tools API。
# """
# import json
# import sys
# import os
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# from agents.base_agent import BaseAgent, extract_json
# from skills.solver_validator.solver_validator import (
#     nearest_neighbor_solution,
#     full_validation_report,
#     improve_with_solver,
#     try_fix_solution,
# )
# from typing import Dict, Any, List


# class SolverValidatorAgent(BaseAgent):

#     def __init__(self, api_key: str):
#         # BaseAgent 读取完整 SKILL.md 作为 system prompt，self.tools 默认为 []
#         super().__init__(api_key, skill_name="solver_validator")

#     # ── Phase 1：生成初始解 ───────────────────────────────────────────────────

#     def _generate_solution(
#         self,
#         instance: Dict[str, Any],
#         feedback: str = "",
#     ) -> Dict[str, Any]:
#         """
#         调用 LLM 输出 Phase 1 solve JSON。

#         feedback 非空时表示上一轮 validate 失败，将结构化违约原因注入 prompt，
#         让 LLM 针对性修正方案（而非通过 function tool 调用启发式）。

#         LLM 可在 solve JSON 中声明 "use_heuristic": true，
#         系统检测到后直接调用本地启发式 fallback。
#         """
#         if feedback:
#             prompt = (
#                 f"【重新生成解 — 上一轮验证失败】\n\n"
#                 f"问题实例：\n```json\n{json.dumps(instance, ensure_ascii=False, indent=2)}\n```\n\n"
#                 f"上一轮违约信息（结构化）：\n{feedback}\n\n"
#                 f"请分析违约原因，生成修正后的方案。"
#                 f"若判断本题适合启发式，可在 JSON 中加 \"use_heuristic\": true。\n"
#                 f"输出 Phase 1 JSON。"
#             )
#         else:
#             prompt = (
#                 f"【Phase 1 — 生成初始解】\n\n"
#                 f"```json\n{json.dumps(instance, ensure_ascii=False, indent=2)}\n```\n\n"
#                 f"输出 Phase 1 JSON。"
#             )

#         raw    = self.run(prompt)
#         result = extract_json(raw)

#         # LLM 声明 use_heuristic 或解析失败 → 本地启发式 fallback
#         if not result or result.get("use_heuristic") or "solution" not in result:
#             fb = nearest_neighbor_solution(instance)
#             fb["reasoning"] = (
#                 "LLM 声明使用启发式" if (result and result.get("use_heuristic"))
#                 else "LLM 输出解析失败，自动使用最近邻启发式算法"
#             )
#             return fb

#         return result

#     # ── Phase 2：本地验证 + Observation 回注 + LLM 输出最终 JSON ─────────────

#     def _run_validate(
#         self,
#         solution: List[List[int]],
#         instance: Dict[str, Any],
#         initial_cost: float,
#     ) -> Dict[str, Any]:
#         """
#         tool-free 验证流程：
#           1. 系统本地执行 full_validation_report() → Observation A
#           2. 若可行：系统本地执行 improve_with_solver() → Observation B
#           3. 把 A + B 注入 prompt，让 LLM 输出 Phase 2 validate JSON
#           4. LLM 解析失败 → 直接用本地结果 fallback
#         """
#         # ── Observation A：可行性检查 ──────────────────────────────────────────
#         check_result = full_validation_report(solution, instance)
#         obs_a = json.dumps(check_result, ensure_ascii=False, indent=2)

#         # ── Observation B：2-opt 优化（仅在可行时执行）────────────────────────
#         improve_result = None
#         obs_b = "（方案不可行，跳过 2-opt 优化）"
#         if check_result.get("feasible"):
#             improve_result = improve_with_solver(solution, instance)
#             obs_b = json.dumps(improve_result, ensure_ascii=False, indent=2)

#         # ── 把 Observation 注入 prompt，让 LLM 输出 validate JSON ─────────────
#         prompt = (
#             f"【Phase 2 — 验证并优化】\n\n"
#             f"## 问题实例\n```json\n{json.dumps(instance, ensure_ascii=False)}\n```\n\n"
#             f"## 当前方案\n```\n{solution}\n```\n\n"
#             f"## Observation A：本地可行性检查结果\n```json\n{obs_a}\n```\n\n"
#             f"## Observation B：2-opt 优化结果\n```json\n{obs_b}\n```\n\n"
#             f"原始基准成本（第一轮方案）：{initial_cost}\n\n"
#             f"请综合 Observation A 和 B，输出 Phase 2 validate JSON。"
#         )
#         raw    = self.run(prompt)
#         result = extract_json(raw)

#         if result and "status" in result:
#             # 补全 original_cost（LLM 有时会遗漏）
#             result.setdefault("original_cost", initial_cost)
#             # 补全 improvement_rate（如果 LLM 没算）
#             fc = result.get("final_cost")
#             if fc is not None and fc < result["original_cost"] and "improvement_rate" not in result:
#                 result["improvement_rate"] = round(
#                     (result["original_cost"] - fc) / result["original_cost"] * 100, 1
#                 )
#             return result

#         # ── LLM 解析失败 → 本地结果直接 fallback ─────────────────────────────
#         if improve_result:
#             final_cost = improve_result.get("cost", initial_cost)
#             final_sol  = improve_result.get("improved_solution", solution)
#             status     = "improved" if final_cost < initial_cost else "feasible"
#         else:
#             final_cost = check_result.get("cost", 9999)
#             final_sol  = solution
#             status     = "infeasible"

#         return {
#             "phase":            "validate",
#             "status":           status,
#             "solution":         final_sol,
#             "original_cost":    initial_cost,
#             "final_cost":       final_cost,
#             "improvement_rate": round(
#                 (initial_cost - final_cost) / initial_cost * 100, 1
#             ) if initial_cost > 0 else 0,
#             "violations":       check_result.get("violations", []),
#             "route_details":    check_result.get("route_details", []),
#             "analysis":         "本地工具直接计算（LLM 输出解析失败）",
#         }

#     # ── 公开接口：solve → validate 自愈循环 ───────────────────────────────────

#     def solve_and_validate(
#         self,
#         instance: Dict[str, Any],
#         max_rounds: int = 3,
#     ) -> Dict[str, Any]:
#         """
#         solve → validate 自愈循环，最多 max_rounds 轮：
#           - validate 通过（feasible / improved）→ 立即返回
#           - validate 失败 → 把结构化违约原因（time_window / capacity / coverage）
#             反馈给 LLM，下轮 solve 时注入 prompt 引导修正
#           - 若违约方案可通过本地规则修复（try_fix_solution），先尝试修复
#           - 达到上限 → 返回最后一次 validate 结果，继续出报告

#         返回值供 KnowledgeAgent 生成最终报告，无论是否可行都会有返回。
#         num_vehicles 使用最终 solution 的实际长度（修复了旧版 bug）。
#         """
#         n = len(instance.get("customers", []))
#         print(
#             f"  [SolverValidatorAgent] 开始 solve→validate 循环，"
#             f"客户数: {n}，最大轮数: {max_rounds}"
#         )

#         feedback: str              = ""    # 上轮结构化违约原因
#         last_result: Dict          = {}
#         initial_cost: float        = None  # 第一轮方案基准成本

#         for round_i in range(1, max_rounds + 1):

#             # ── Phase 1: Solve ──────────────────────────────────────────────
#             print(f"\n  [Round {round_i}/{max_rounds}] Solve...")
#             solver_result = self._generate_solution(instance, feedback)
#             solution      = solver_result.get("solution", [])
#             print(f"  [Round {round_i}] 生成解: {len(solution)} 辆车  {solution}")

#             # 第一轮记录基准成本
#             if initial_cost is None:
#                 quick        = full_validation_report(solution, instance)
#                 initial_cost = quick.get("cost", 9999)

#             # ── Phase 2: Validate ───────────────────────────────────────────
#             print(f"  [Round {round_i}/{max_rounds}] Validate...")
#             val_result = self._run_validate(solution, instance, initial_cost)
#             status     = val_result.get("status", "infeasible")
#             violations = val_result.get("violations", [])
#             print(
#                 f"  [Round {round_i}] 验证结果: {status}  "
#                 f"cost={val_result.get('final_cost')}  violations={violations}"
#             )

#             # 附加求解元信息（用于报告）
#             # num_vehicles 取最终 solution 实际长度，而非 solve 阶段长度
#             final_sol = val_result.get("solution", solution)
#             val_result["solver_reasoning"] = solver_result.get("reasoning", "")
#             val_result["num_vehicles"]      = len(final_sol)
#             last_result = val_result

#             if status in ("feasible", "improved"):
#                 print(f"  [SolverValidatorAgent] ✅ 第 {round_i} 轮通过，停止循环")
#                 break

#             # ── 尝试本地规则修复（先于 LLM 重试，节省 token）──────────────────
#             if violations and round_i < max_rounds:
#                 fixed = try_fix_solution(solution, instance, violations)
#                 fixed_check = full_validation_report(fixed, instance)
#                 if fixed_check.get("feasible"):
#                     print(f"  [Round {round_i}] 本地规则修复成功，跳过 LLM 重试")
#                     improved = improve_with_solver(fixed, instance)
#                     fc       = improved.get("cost", fixed_check["cost"])
#                     last_result = {
#                         "phase":            "validate",
#                         "status":           "improved" if fc < initial_cost else "feasible",
#                         "solution":         improved.get("improved_solution", fixed),
#                         "original_cost":    initial_cost,
#                         "final_cost":       fc,
#                         "improvement_rate": round(
#                             (initial_cost - fc) / initial_cost * 100, 1
#                         ) if initial_cost > 0 else 0,
#                         "violations":       [],
#                         "route_details":    fixed_check.get("route_details", []),
#                         "analysis":         "本地规则修复 + 2-opt 优化",
#                         "solver_reasoning": solver_result.get("reasoning", ""),
#                         "num_vehicles":     len(improved.get("improved_solution", fixed)),
#                     }
#                     print(f"  [SolverValidatorAgent] ✅ 本地修复通过，停止循环")
#                     break

#             # ── 构造结构化 feedback，分类型方便 LLM 定向修正 ──────────────────
#             time_window_viols = [v for v in violations if "时间窗" in v]
#             capacity_viols    = [v for v in violations if "容量" in v]
#             coverage_viols    = [v for v in violations if "遗漏" in v]
#             other_viols       = [
#                 v for v in violations
#                 if v not in time_window_viols + capacity_viols + coverage_viols
#             ]

#             feedback_parts = [f"第 {round_i} 轮方案验证失败，违约明细："]
#             if time_window_viols:
#                 feedback_parts.append(
#                     f"  [时间窗违约] {'; '.join(time_window_viols)}\n"
#                     f"  → 建议：将违约节点移至独立路线头部单独服务"
#                 )
#             if capacity_viols:
#                 feedback_parts.append(
#                     f"  [容量违约]   {'; '.join(capacity_viols)}\n"
#                     f"  → 建议：将末尾节点转移到负载最轻的路线"
#                 )
#             if coverage_viols:
#                 feedback_parts.append(
#                     f"  [覆盖缺失]   {'; '.join(coverage_viols)}\n"
#                     f"  → 建议：为遗漏客户单独开辟新路线"
#                 )
#             if other_viols:
#                 feedback_parts.append(f"  [其他违约]   {'; '.join(other_viols)}")
#             feedback_parts.append("请在下一轮针对以上问题重新生成方案。")
#             feedback = "\n".join(feedback_parts)

#             if round_i == max_rounds:
#                 print(
#                     f"  [SolverValidatorAgent] ⚠️  达到最大轮数 {max_rounds}，"
#                     f"最终状态: {status}，继续出报告"
#                 )

#         return last_result

# agents/solver_validator_agent.py
import json
from typing import Dict, Any, List, Tuple, Optional

from agents.base_agent import BaseAgent, extract_json
from skills.solver_validator.solver_validator import (
    nearest_neighbor_solution,
    full_validation_report,
    improve_with_solver,
    try_fix_solution,
)


def _categorize_violations(violations: List[str]) -> Dict[str, List[str]]:
    cats = {"time_window": [], "capacity": [], "coverage": [], "unknown": []}
    for v in violations or []:
        if "时间窗违约" in v:
            cats["time_window"].append(v)
        elif "容量违约" in v:
            cats["capacity"].append(v)
        elif "遗漏客户" in v or "未知客户" in v:
            cats["coverage"].append(v)
        else:
            cats["unknown"].append(v)
    return cats


def _local_repair(solution: List[List[int]], instance: Dict[str, Any], violations: List[str]) -> Tuple[bool, List[List[int]]]:
    """Local self-healing attempt using the shared skill implementation.

    Delegates to skills.solver_validator.try_fix_solution so the repair logic
    stays consistent between the skill module and the agent loop.
    """
    if not solution:
        return False, solution
    repaired = try_fix_solution(solution, instance, violations or [])
    return repaired != solution, repaired


class SolverValidatorAgent(BaseAgent):
    """Tool-free self-healing solve/validate loop.

    - LLM outputs structured JSON for Phase 1 (solve)
    - local validator produces feasibility + structured feedback
    - if infeasible, feedback is injected and LLM regenerates
    - if feasible, local 2-opt is applied
    """

    def __init__(self, api_key: str):
        super().__init__(api_key, skill_name='solver_validator')

    def _generate_solution(self, instance: Dict[str, Any], feedback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if feedback:
            prompt = (
                "【Phase 1 — 生成初始解（上一轮验证失败，带结构化反馈）】\n\n"
                f"实例：\n```json\n{json.dumps(instance, ensure_ascii=False, indent=2)}\n```\n\n"
                f"结构化反馈：\n```json\n{json.dumps(feedback, ensure_ascii=False, indent=2)}\n```\n\n"
                "请根据反馈修复方案（必要时可将问题点拆分成新路线），输出 Phase 1 JSON。"
            )
        else:
            prompt = (
                "【Phase 1 — 生成初始解】\n\n"
                f"```json\n{json.dumps(instance, ensure_ascii=False, indent=2)}\n```\n\n"
                "输出 Phase 1 JSON。"
            )

        raw = self.run(prompt)
        parsed = extract_json(raw)
        if parsed and isinstance(parsed.get('solution'), list):
            # normalize num_vehicles
            parsed['num_vehicles'] = int(parsed.get('num_vehicles') or len(parsed['solution']))
            return parsed

        # fallback to heuristic
        fb = nearest_neighbor_solution(instance)
        fb['phase'] = 'solve'
        fb['reasoning'] = 'LLM 输出解析失败，回退到最近邻启发式'
        fb['num_vehicles'] = len(fb.get('solution', []))
        return fb

    def _validate_and_optimize(self, solution: List[List[int]], instance: Dict[str, Any]) -> Dict[str, Any]:
        report = full_validation_report(solution, instance)
        if report.get('feasible'):
            original_cost = float(report.get('cost') or 0)
            improved = improve_with_solver(solution, instance)
            improved_solution = improved.get('improved_solution', solution)
            # IMPORTANT: recompute final route details/cost on the improved solution
            final_report = full_validation_report(improved_solution, instance)
            final_cost = float(final_report.get('cost') or improved.get('cost') or original_cost)
            status = 'improved' if final_cost < original_cost - 1e-6 else 'feasible'
            rate = round((original_cost - final_cost) / original_cost * 100, 1) if original_cost > 0 else 0
            return {
                'phase': 'validate',
                'status': status,
                'solution': improved_solution,
                'original_cost': original_cost,
                'final_cost': final_cost,
                'improvement_rate': rate,
                'violations': [],
                'route_details': final_report.get('route_details', []),
                '_validator_report': final_report,
            }

        # infeasible
        return {
            'phase': 'validate',
            'status': 'infeasible',
            'solution': solution,
            'original_cost': float(report.get('cost') or 0),
            'final_cost': float(report.get('cost') or 0),
            'improvement_rate': 0,
            'violations': report.get('violations', []),
            'route_details': report.get('route_details', []),
            '_validator_report': report,
        }

    def solve_and_validate(self, instance: Dict[str, Any], max_rounds: int = 6) -> Dict[str, Any]:
        print(f"  [SolverValidatorAgent] solve→validate loop | max_rounds={max_rounds} | customers={len(instance.get('customers', []))}")

        feedback_struct: Optional[Dict[str, Any]] = None
        last: Dict[str, Any] = {}
        solver_reasoning = ''

        for r in range(1, max_rounds + 1):
            print(f"\n  [Round {r}/{max_rounds}] Solve")
            solve_out = self._generate_solution(instance, feedback_struct)
            solution = solve_out.get('solution', [])
            solver_reasoning = solve_out.get('reasoning', '')
            print(f"  [Round {r}] solution routes={len(solution)}")

            print(f"  [Round {r}/{max_rounds}] Validate(local)")
            val = self._validate_and_optimize(solution, instance)
            val['solver_reasoning'] = solver_reasoning
            val['num_vehicles'] = len(val.get('solution', []))
            last = val

            if val.get('status') in ('feasible', 'improved'):
                print(f"  [SolverValidatorAgent] ✅ feasible at round {r}")
                break

            violations = val.get('violations', [])
            cats = _categorize_violations(violations)

            # local quick repair attempt before asking LLM again
            changed, repaired = _local_repair(solution, instance, violations)
            if changed:
                repaired_val = self._validate_and_optimize(repaired, instance)
                repaired_val['solver_reasoning'] = solver_reasoning + ' | local_repair'
                repaired_val['num_vehicles'] = len(repaired_val.get('solution', []))
                last = repaired_val
                if repaired_val.get('status') in ('feasible', 'improved'):
                    print(f"  [SolverValidatorAgent] ✅ feasible after local repair at round {r}")
                    break

            feedback_struct = {
                'round': r,
                'violation_categories': cats,
                'raw_violations': violations,
                'repair_hint': '优先处理 time_window/capacity/coverage 三类问题；可拆分为更多路线以恢复可行性。',
            }

            if r == max_rounds:
                print(f"  [SolverValidatorAgent] ⚠️ reached max_rounds={max_rounds} (still infeasible)")

        return last
