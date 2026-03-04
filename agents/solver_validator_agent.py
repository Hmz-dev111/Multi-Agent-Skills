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
