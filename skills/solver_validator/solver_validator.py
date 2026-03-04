# # skills/solver_validator/solver_validator.py
# """
# solver_validator 技能的代码实现
# 包含：
#   - 最近邻启发式初始解生成（供 SolverValidatorAgent fallback 使用）
#   - CVRPTW 完整可行性检查（供 validate 阶段工具调用）
#   - 2-opt 模拟优化（供 validate 阶段工具调用）
# """
# import math
# import re
# import copy
# from typing import List, Dict, Any, Optional

# # ── 基础几何计算 ──────────────────────────────────────────────────────────────

# def euclidean(p1: Dict, p2: Dict) -> float:
#     """计算欧几里得距离"""
#     return math.sqrt((p1['x'] - p2['x']) ** 2 + (p1['y'] - p2['y']) ** 2)

# def calculate_route_cost(route: List[int], instance: Dict[str, Any]) -> float:
#     """计算单条路径的真实行驶距离（含回程）"""
#     if not route: return 0.0
#     depot = instance['depot']
#     customers = {c['id']: c for c in instance['customers']}
    
#     dist = 0.0
#     prev = depot
#     for cid in route:
#         curr = customers[cid]
#         dist += euclidean(prev, curr)
#         prev = curr
#     dist += euclidean(prev, depot)
#     return dist

# # ── 启发式初始解 (Nearest Neighbor) ──────────────────────────────────────────

# def nearest_neighbor_solution(instance: Dict[str, Any]) -> Dict[str, Any]:
#     """改进的最近邻启发式：严格遵守容量和时间窗"""
#     depot = instance['depot']
#     capacity = instance['capacity']
#     customers = {c['id']: c for c in instance['customers']}
#     unvisited = set(customers.keys())
#     routes = []

#     while unvisited:
#         route = []
#         curr_loc = depot
#         curr_time = 0.0
#         curr_load = 0.0
        
#         while True:
#             best_cid = None
#             min_dist = float('inf')
            
#             for cid in unvisited:
#                 c = customers[cid]
#                 dist = euclidean(curr_loc, c)
#                 arrival = max(curr_time + dist, c['ready'])
                
#                 # 约束检查：容量 + 到达时间不能超过 due
#                 if curr_load + c['demand'] <= capacity and arrival <= c['due']:
#                     if dist < min_dist:
#                         min_dist = dist
#                         best_cid = cid
            
#             if best_cid is None: break
            
#             # 更新状态
#             c = customers[best_cid]
#             dist = euclidean(curr_loc, c)
#             curr_time = max(curr_time + dist, c['ready']) + c['service']
#             curr_load += c['demand']
#             curr_loc = c
#             route.append(best_cid)
#             unvisited.remove(best_cid)
            
#         if route:
#             routes.append(route)
#         else:
#             # 如果存在无法通过约束到达的点，强制开启新车（异常处理）
#             forced_id = next(iter(unvisited))
#             routes.append([forced_id])
#             unvisited.remove(forced_id)

#     return {
#         "solution": routes,
#         "num_vehicles": len(routes),
#         "reasoning": f"使用改进最近邻启发式生成，共使用 {len(routes)} 辆车。"
#     }

# # ── 完整可行性检查 ────────────────────────────────────────────────────────────

# def full_validation_report(solution: List[List[int]], instance: Dict[str, Any]) -> Dict[str, Any]:
#     """严格的可行性验证，返回详细的违约报告"""
#     if not solution or not isinstance(solution, list):
#         return {"feasible": False, "violations": ["无效的方案格式"], "cost": 0, "route_details": []}

#     depot = instance['depot']
#     capacity = instance['capacity']
#     customers = {c['id']: c for c in instance['customers']}
    
#     total_dist = 0.0
#     violations = []
#     route_details = []
#     visited_ids = []

#     for idx, route in enumerate(solution):
#         r_load = 0.0
#         r_time = 0.0
#         r_dist = 0.0
#         prev = depot
#         stops_info = []

#         for cid in route:
#             if cid not in customers:
#                 violations.append(f"路线 {idx+1} 包含未知客户 ID: {cid}")
#                 continue
            
#             c = customers[cid]
#             d = euclidean(prev, c)
#             arrival = r_time + d
            
#             # 记录时间窗违约
#             if arrival > c['due']:
#                 violations.append(f"时间窗违约 at {cid}: 到达 {arrival:.1f} > 最晚 {c['due']}")
            
#             # 即使早到也要等待
#             start_service = max(arrival, c['ready'])
#             r_dist += d
#             r_time = start_service + c['service']
#             r_load += c['demand']
#             visited_ids.append(cid)
#             prev = c
        
#         # 回到仓库
#         back_to_depot = euclidean(prev, depot)
#         r_dist += back_to_depot
#         total_dist += r_dist

#         # 记录容量违约
#         if r_load > capacity:
#             violations.append(f"容量违约 on route {idx+1}: {r_load} > {capacity}")

#         route_details.append({
#             "route_id": idx + 1,
#             "stops": route,
#             "distance": round(r_dist, 2),
#             "load": r_load
#         })

#     # 检查是否覆盖所有客户
#     all_target_ids = set(customers.keys())
#     missing = all_target_ids - set(visited_ids)
#     if missing:
#         violations.append(f"遗漏客户: {list(missing)}")

#     return {
#         "feasible": len(violations) == 0,
#         "violations": violations,
#         "cost": round(total_dist, 2),
#         "num_routes": len(solution),
#         "route_details": route_details
#     }

# # ── 2-Opt 局部搜索优化 ────────────────────────────────────────────────────────

# def improve_with_solver(solution: List[List[int]], instance: Dict[str, Any]) -> Dict[str, Any]:
#     """真正的 2-Opt 算法：在不违反约束的前提下优化每条路径"""
#     optimized_solution = copy.deepcopy(solution)
    
#     for r_idx, route in enumerate(optimized_solution):
#         if len(route) < 2: continue
        
#         improved = True
#         while improved:
#             improved = False
#             best_dist = calculate_route_cost(route, instance)
            
#             for i in range(len(route)):
#                 for j in range(i + 1, len(route)):
#                     # 尝试翻转段 [i:j+1]
#                     new_route = route[:i] + route[i:j+1][::-1] + route[j+1:]
                    
#                     # 检查新路径是否依然满足时间窗约束（核心：2-opt 往往会破坏 TW）
#                     if _is_route_feasible(new_route, instance):
#                         new_dist = calculate_route_cost(new_route, instance)
#                         if new_dist < best_dist - 0.01: # 避免浮点数精度问题
#                             route[:] = new_route
#                             best_dist = new_dist
#                             improved = True
                            
#     final_report = full_validation_report(optimized_solution, instance)
#     return {
#         "improved_solution": optimized_solution,
#         "cost": final_report["cost"],
#         "feasible": final_report["feasible"]
#     }

# def _is_route_feasible(route: List[int], instance: Dict[str, Any]) -> bool:
#     """快速检查单条路径的可行性"""
#     depot = instance['depot']
#     capacity = instance['capacity']
#     customers = {c['id']: c for c in instance['customers']}
    
#     load = 0.0
#     time = 0.0
#     prev = depot
#     for cid in route:
#         c = customers[cid]
#         dist = euclidean(prev, c)
#         arrival = time + dist
#         if arrival > c['due']: return False
#         time = max(arrival, c['ready']) + c['service']
#         load += c['demand']
#         prev = c
#     return load <= capacity

# # ── 自动修复逻辑 ──────────────────────────────────────────────────────────────

# def try_fix_solution(solution: List[List[int]], instance: Dict[str, Any], violations: List[str]) -> List[List[int]]:
#     """
#     智能修复：
#     1. 识别违约节点。
#     2. 将违约节点剥离，尝试重新插入或建立新路径。
#     """
#     customers_dict = {c['id']: c for c in instance['customers']}
    
#     # 从违约信息中提取 ID（兼容正则）
#     bad_nodes = set()
#     for v in violations:
#         m = re.search(r'at (\d+)', v)
#         if m: bad_nodes.add(int(m.group(1)))
    
#     if not bad_nodes: return solution

#     # 剥离坏节点
#     cleaned_solution = []
#     to_reassign = list(bad_nodes)
#     for route in solution:
#         new_route = [n for n in route if n not in bad_nodes]
#         if new_route: cleaned_solution.append(new_route)

#     # 尝试将坏节点作为新路径加入（最安全且保证可行性的做法）
#     # 在进阶版本中，这里可以写 Best-Fit 插入算法
#     for node_id in to_reassign:
#         cleaned_solution.append([node_id])
    
#     return cleaned_solution

# skills/solver_validator/solver_validator.py
"""
solver_validator 技能的代码实现
包含：
  - 最近邻启发式初始解生成（供 SolverValidatorAgent fallback 使用）
  - CVRPTW 完整可行性检查（供 validate 阶段工具调用）
  - 2-opt 模拟优化（供 validate 阶段工具调用）
"""
import math
import re
import copy
from typing import List, Dict, Any, Optional

# ── 基础几何计算 ──────────────────────────────────────────────────────────────

def euclidean(p1: Dict, p2: Dict) -> float:
    """计算欧几里得距离"""
    return math.sqrt((p1['x'] - p2['x']) ** 2 + (p1['y'] - p2['y']) ** 2)

def calculate_route_cost(route: List[int], instance: Dict[str, Any]) -> float:
    """计算单条路径的真实行驶距离（含回程）"""
    if not route: return 0.0
    depot = instance['depot']
    customers = {c['id']: c for c in instance['customers']}
    
    dist = 0.0
    prev = depot
    for cid in route:
        curr = customers[cid]
        dist += euclidean(prev, curr)
        prev = curr
    dist += euclidean(prev, depot)
    return dist

# ── 启发式初始解 (Nearest Neighbor) ──────────────────────────────────────────

def nearest_neighbor_solution(instance: Dict[str, Any]) -> Dict[str, Any]:
    """改进的最近邻启发式：严格遵守容量和时间窗"""
    depot = instance['depot']
    capacity = instance['capacity']
    customers = {c['id']: c for c in instance['customers']}
    unvisited = set(customers.keys())
    routes = []

    while unvisited:
        route = []
        curr_loc = depot
        curr_time = 0.0
        curr_load = 0.0
        
        while True:
            best_cid = None
            min_dist = float('inf')
            
            for cid in unvisited:
                c = customers[cid]
                dist = euclidean(curr_loc, c)
                arrival = max(curr_time + dist, c['ready'])
                
                # 约束检查：容量 + 到达时间不能超过 due
                if curr_load + c['demand'] <= capacity and arrival <= c['due']:
                    if dist < min_dist:
                        min_dist = dist
                        best_cid = cid
            
            if best_cid is None: break
            
            # 更新状态
            c = customers[best_cid]
            dist = euclidean(curr_loc, c)
            curr_time = max(curr_time + dist, c['ready']) + c['service']
            curr_load += c['demand']
            curr_loc = c
            route.append(best_cid)
            unvisited.remove(best_cid)
            
        if route:
            routes.append(route)
        else:
            # 如果存在无法通过约束到达的点，强制开启新车（异常处理）
            forced_id = next(iter(unvisited))
            routes.append([forced_id])
            unvisited.remove(forced_id)

    return {
        "solution": routes,
        "num_vehicles": len(routes),
        "reasoning": f"使用改进最近邻启发式生成，共使用 {len(routes)} 辆车。"
    }

# ── 完整可行性检查 ────────────────────────────────────────────────────────────

def full_validation_report(solution: List[List[int]], instance: Dict[str, Any]) -> Dict[str, Any]:
    """严格的可行性验证，返回详细的违约报告"""
    if not solution or not isinstance(solution, list):
        return {"feasible": False, "violations": ["无效的方案格式"], "cost": 0, "route_details": []}

    depot = instance['depot']
    capacity = instance['capacity']
    customers = {c['id']: c for c in instance['customers']}
    
    total_dist = 0.0
    violations = []
    route_details = []
    visited_ids = []

    for idx, route in enumerate(solution):
        r_load = 0.0
        r_time = 0.0
        r_dist = 0.0
        prev = depot
        stops_info = []

        for cid in route:
            if cid not in customers:
                violations.append(f"路线 {idx+1} 包含未知客户 ID: {cid}")
                continue
            
            c = customers[cid]
            d = euclidean(prev, c)
            arrival = r_time + d
            
            # 记录时间窗违约
            if arrival > c['due']:
                violations.append(f"时间窗违约 at {cid}: 到达 {arrival:.1f} > 最晚 {c['due']}")
            
            # 即使早到也要等待
            start_service = max(arrival, c['ready'])
            r_dist += d
            r_time = start_service + c['service']
            r_load += c['demand']
            visited_ids.append(cid)
            prev = c
        
        # 回到仓库
        back_to_depot = euclidean(prev, depot)
        r_dist += back_to_depot
        total_dist += r_dist

        # 记录容量违约
        if r_load > capacity:
            violations.append(f"容量违约 on route {idx+1}: {r_load} > {capacity}")

        route_details.append({
            "route_id": idx + 1,
            "stops": route,
            "distance": round(r_dist, 2),
            "load": r_load
        })

    # 检查是否覆盖所有客户
    all_target_ids = set(customers.keys())
    missing = all_target_ids - set(visited_ids)
    if missing:
        violations.append(f"遗漏客户: {list(missing)}")

    return {
        "feasible": len(violations) == 0,
        "violations": violations,
        "cost": round(total_dist, 2),
        "num_routes": len(solution),
        "route_details": route_details
    }

# ── 2-Opt 局部搜索优化 ────────────────────────────────────────────────────────

def improve_with_solver(solution: List[List[int]], instance: Dict[str, Any]) -> Dict[str, Any]:
    """真正的 2-Opt 算法：在不违反约束的前提下优化每条路径"""
    optimized_solution = copy.deepcopy(solution)
    
    for r_idx, route in enumerate(optimized_solution):
        if len(route) < 2: continue
        
        improved = True
        while improved:
            improved = False
            best_dist = calculate_route_cost(route, instance)
            
            for i in range(len(route)):
                for j in range(i + 1, len(route)):
                    # 尝试翻转段 [i:j+1]
                    new_route = route[:i] + route[i:j+1][::-1] + route[j+1:]
                    
                    # 检查新路径是否依然满足时间窗约束（核心：2-opt 往往会破坏 TW）
                    if _is_route_feasible(new_route, instance):
                        new_dist = calculate_route_cost(new_route, instance)
                        if new_dist < best_dist - 0.01: # 避免浮点数精度问题
                            route[:] = new_route
                            best_dist = new_dist
                            improved = True
                            
    final_report = full_validation_report(optimized_solution, instance)
    return {
        "improved_solution": optimized_solution,
        "cost": final_report["cost"],
        "feasible": final_report["feasible"]
    }

def _is_route_feasible(route: List[int], instance: Dict[str, Any]) -> bool:
    """快速检查单条路径的可行性"""
    depot = instance['depot']
    capacity = instance['capacity']
    customers = {c['id']: c for c in instance['customers']}
    
    load = 0.0
    time = 0.0
    prev = depot
    for cid in route:
        c = customers[cid]
        dist = euclidean(prev, c)
        arrival = time + dist
        if arrival > c['due']: return False
        time = max(arrival, c['ready']) + c['service']
        load += c['demand']
        prev = c
    return load <= capacity

# ── 自动修复逻辑 ──────────────────────────────────────────────────────────────

def try_fix_solution(solution: List[List[int]], instance: Dict[str, Any], violations: List[str]) -> List[List[int]]:
    """
    智能修复：
    1. 识别违约节点。
    2. 将违约节点剥离，尝试重新插入或建立新路径。
    """
    customers_dict = {c['id']: c for c in instance['customers']}

    # --- 1) Parse violations into actionable sets ---
    bad_nodes: set[int] = set()
    missing_nodes: set[int] = set()
    overloaded_routes: set[int] = set()  # 1-based route index

    for v in violations:
        # time-window violations: "时间窗违约 at {cid}"
        m = re.search(r"at\s+(\d+)", v)
        if m:
            bad_nodes.add(int(m.group(1)))

        # missing customers: "遗漏客户: [..]"
        m2 = re.search(r"遗漏客户\s*:\s*\[(.*?)\]", v)
        if m2:
            for tok in re.split(r"[\s,]+", m2.group(1).strip()):
                tok = tok.strip().strip('"\'')
                if tok.isdigit():
                    missing_nodes.add(int(tok))

        # capacity violation: "容量违约 on route X"
        m3 = re.search(r"容量违约\s+on\s+route\s+(\d+)", v)
        if m3:
            overloaded_routes.add(int(m3.group(1)))

    # also treat missing nodes as nodes to reassign
    to_reassign = list((bad_nodes | missing_nodes) & set(customers_dict.keys()))

    # If nothing to fix, return original
    if not to_reassign and not overloaded_routes:
        return solution

    # --- 2) Remove nodes that must be reassigned (time-window/missing) ---
    cleaned_solution: List[List[int]] = []
    removed: set[int] = set(to_reassign)
    for r in solution:
        nr = [n for n in r if n not in removed]
        if nr:
            cleaned_solution.append(nr)

    # --- 3) Simple capacity repair: for overloaded routes, pop tail nodes into reassignment ---
    if overloaded_routes:
        cap = instance['capacity']
        for ridx in sorted(overloaded_routes):
            i = ridx - 1
            if i < 0 or i >= len(cleaned_solution):
                continue
            # keep removing from end until feasible
            while cleaned_solution[i] and not _is_route_feasible(cleaned_solution[i], instance):
                moved = cleaned_solution[i].pop()
                if moved in customers_dict:
                    removed.add(moved)
        cleaned_solution = [r for r in cleaned_solution if r]

    # update reassignment list
    to_reassign = list(removed)

    # --- 4) Try greedy insertion into existing routes (best-effort) ---
    def _try_insert(node: int) -> bool:
        best_r = None
        best_pos = None
        best_delta = float('inf')
        for r_idx, r in enumerate(cleaned_solution):
            for pos in range(len(r) + 1):
                cand = r[:pos] + [node] + r[pos:]
                if _is_route_feasible(cand, instance):
                    # delta distance as heuristic
                    old = calculate_route_cost(r, instance)
                    new = calculate_route_cost(cand, instance)
                    delta = new - old
                    if delta < best_delta:
                        best_delta, best_r, best_pos = delta, r_idx, pos
        if best_r is None:
            return False
        cleaned_solution[best_r] = cleaned_solution[best_r][:best_pos] + [node] + cleaned_solution[best_r][best_pos:]
        return True

    remaining: List[int] = []
    for node in to_reassign:
        if not _try_insert(node):
            remaining.append(node)

    # --- 5) Any nodes we still can't insert safely become single-customer routes ---
    for node in remaining:
        cleaned_solution.append([node])

    return cleaned_solution