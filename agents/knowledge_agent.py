# # # agents/knowledge_agent.py
# # import json
# # import os
# # import sys
# # from datetime import datetime
# # sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# # from agents.base_agent import BaseAgent, extract_json
# # # 直接从 skill 文件夹内的 knowledge_report.py 导入代码实现
# # from skills.knowledge_report.knowledge_report import (
# #     retrieve,
# #     format_for_prompt,
# #     save_json,
# #     save_docx
# # )
# # from typing import Dict, Any, Optional
# # from dotenv import load_dotenv

# # load_dotenv()

# # try:
# #     from firecrawl import Firecrawl
# #     firecrawl = Firecrawl(api_key="fc-xx")
# # except ImportError:
# #     firecrawl = None

# # KNOWLEDGE_TOOLS = [
# #     {
# #         "type": "function",
# #         "function": {
# #             "name": "search_documents",
# #             "description": "从本地 CVRPTW 知识库检索相关文档片段",
# #             "parameters": {
# #                 "type": "object",
# #                 "properties": {
# #                     "query": {"type": "string"},
# #                     "top_k": {"type": "integer", "default": 5}
# #                 },
# #                 "required": ["query"]
# #             }
# #         }
# #     },
# #     {
# #         "type": "function",
# #         "function": {
# #             "name": "web_search",
# #             "description": "通过 Firecrawl 搜索互联网获取最新 CVRPTW 信息",
# #             "parameters": {
# #                 "type": "object",
# #                 "properties": {
# #                     "query":       {"type": "string"},
# #                     "num_results": {"type": "integer", "default": 3}
# #                 },
# #                 "required": ["query"]
# #             }
# #         }
# #     }
# # ]

# # class KnowledgeAgent(BaseAgent):

# #     def __init__(self, api_key: str, output_dir: str = "output"):
# #         super().__init__(api_key, skill_name="knowledge_report")
# #         self.tools      = KNOWLEDGE_TOOLS
# #         self.output_dir = output_dir
# #         self._cached_knowledge: Optional[Dict] = None
# #         self._web_search_used: bool = False   # 记录 retrieve 阶段是否使用了 web_search

# #     def _handle_tool_call(self, name: str, args: Dict[str, Any]) -> str:
# #         if name == "search_documents":
# #             docs = retrieve(args.get("query", ""), args.get("top_k", 5))
# #             return format_for_prompt(docs) if docs else "本地知识库暂无相关内容。"

# #         if name == "web_search":
# #             self._web_search_used = True   # 标记已使用 web_search
# #             if not firecrawl:
# #                 return "FIRECRAWL_API_KEY 未配置，跳过网络搜索。"
# #             try:
# #                 response = firecrawl.search(query=args.get("query", ""), limit=args.get("num_results", 3))
# #                 items = (getattr(response, "web", None)
# #                          or getattr(response, "data", None)
# #                          or (response if isinstance(response, list) else []))
# #                 if not items:
# #                     return "未找到相关搜索结果。"
# #                 results = []
# #                 for item in items:
# #                     t = item.get("title", "无标题") if isinstance(item, dict) else getattr(item, "title", "无标题")
# #                     u = item.get("url", "")        if isinstance(item, dict) else getattr(item, "url", "")
# #                     c = (item.get("markdown") or item.get("description") or "无内容") if isinstance(item, dict) \
# #                         else (getattr(item, "markdown", None) or getattr(item, "description", "无内容"))
# #                     results.append(f"【{t}】\n链接: {u}\n{c[:600]}{'...' if len(c)>600 else ''}")
# #                 return "\n\n---\n\n".join(results)
# #             except Exception as e:
# #                 return f"Firecrawl 搜索失败: {e}"
# #         return f"未知工具: {name}"

# #     def retrieve_context(self, instance: Dict[str, Any]) -> Dict[str, Any]:
# #         n = len(instance.get("customers", []))
# #         print(f"  [KnowledgeAgent/retrieve] 开始检索，规模: {n} 个客户")
# #         self._web_search_used = False   # 每次 retrieve 重置标记
# #         raw    = self.run(
# #             f"【Phase 1 — 知识检索】\n\n"
# #             f"问题特征：{n} 个客户，容量 {instance.get('capacity')}。\n"
# #             f"实例摘要：{json.dumps(instance, ensure_ascii=False)[:400]}...\n\n"
# #             f"请检索并输出 Phase 1 JSON。"
# #         )
# #         result = extract_json(raw)
# #         if result:
# #             print(f"  [KnowledgeAgent/retrieve] 分类: {result.get('instance_classification', 'N/A')}")
# #             print(f"  [KnowledgeAgent/retrieve] web_search 已使用: {self._web_search_used}")
# #             result["_web_search_used"] = self._web_search_used   # 传递给 report 阶段
# #             self._cached_knowledge = result
# #             return result
# #         # Fallback
# #         docs = retrieve(f"CVRPTW {n} customers time window vehicle routing", top_k=3)
# #         fb   = {
# #             "phase": "retrieve",
# #             "knowledge_summary":      format_for_prompt(docs) if docs else "暂无相关知识",
# #             "instance_classification": f"规模：{n} 个客户，容量：{instance.get('capacity')}",
# #             "benchmark_reference":    None,
# #             "algorithm_suggestion":   "建议使用最近邻启发式 + 2-opt 局部搜索",
# #             "sources":                [d["source"] for d in docs],
# #             "_web_search_used":       False
# #         }
# #         self._cached_knowledge = fb
# #         return fb

# #     def generate_report(
# #         self,
# #         instance:         Dict[str, Any],
# #         solver_result:    Dict[str, Any],
# #         validator_result: Dict[str, Any],
# #         knowledge:        Optional[Dict[str, Any]] = None
# #     ) -> Dict[str, str]:
# #         rag_ctx = knowledge or self._cached_knowledge or {}
# #         print(f"  [KnowledgeAgent/report] 开始生成报告...")

# #         # 若 retrieve 阶段未使用 web_search，此处补充一次，丰富报告背景
# #         web_supplement = ""
# #         if not rag_ctx.get("_web_search_used", False) and firecrawl:
# #             n              = len(instance.get("customers", []))
# #             classification = rag_ctx.get("instance_classification", "CVRPTW")
# #             search_query   = f"CVRPTW {n} customers solution benchmark {classification}"
# #             print(f"  [KnowledgeAgent/report] retrieve 未使用 web_search，补充搜索: '{search_query}'")
# #             web_result = self._handle_tool_call("web_search", {"query": search_query, "num_results": 2})
# #             if not web_result.startswith("FIRECRAWL") and not web_result.startswith("未找到"):
# #                 web_supplement = f"\n\n## 补充 Web 搜索结果（报告阶段）\n{web_result}"
# #                 print(f"  [KnowledgeAgent/report] 补充搜索完成，长度: {len(web_result)} 字符")
# #         elif not rag_ctx.get("_web_search_used", False):
# #             print(f"  [KnowledgeAgent/report] retrieve 未使用 web_search，但 Firecrawl 未配置，跳过补充搜索")

# #         raw = self.run(
# #             f"【Phase 2 — 生成分析报告】\n\n"
# #             f"## 问题实例\n```json\n{json.dumps(instance, ensure_ascii=False, indent=2)}\n```\n\n"
# #             f"## 初始解（Solver Phase 1）\n```json\n{json.dumps(solver_result, ensure_ascii=False, indent=2)}\n```\n\n"
# #             f"## 验证优化结果（Solver Phase 2）\n```json\n{json.dumps(validator_result, ensure_ascii=False, indent=2)}\n```\n\n"
# #             f"## 知识检索结果（Retrieve Phase）\n```json\n{json.dumps(rag_ctx, ensure_ascii=False, indent=2)}\n```"
# #             f"{web_supplement}\n\n"
# #             f"请综合以上所有信息，输出 Phase 2 JSON 报告。"
# #         )
# #         report_data = extract_json(raw) or self._build_fallback_report(instance, solver_result, validator_result, rag_ctx)
# #         report_data["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# #         os.makedirs(self.output_dir, exist_ok=True)
# #         json_path = save_json(report_data, self.output_dir)
# #         print(f"  [KnowledgeAgent/report] JSON: {json_path}")
# #         docx_path = None
# #         try:
# #             docx_path = save_docx(report_data, self.output_dir)
# #             print(f"  [KnowledgeAgent/report] DOCX: {docx_path}")
# #         except Exception as e:
# #             print(f"  [KnowledgeAgent/report] DOCX 生成失败: {e}")
# #         return {"json_path": json_path, "docx_path": docx_path, "report_data": report_data}

# #     def _build_fallback_report(self, instance, solver_result, validator_result, rag_ctx) -> Dict[str, Any]:
# #         return {
# #             "phase": "report", "title": "CVRPTW 求解分析报告",
# #             "problem_summary": {
# #                 "num_customers":    len(instance.get("customers", [])),
# #                 "vehicle_capacity": instance.get("capacity", "N/A"),
# #                 "instance_type":    rag_ctx.get("instance_classification", "未分类")
# #             },
# #             "solving_process": {
# #                 "reasoning":        solver_result.get("reasoning", "N/A"),
# #                 "initial_solution": solver_result.get("solution", []),
# #                 "initial_cost":     validator_result.get("original_cost", "N/A")
# #             },
# #             "validation_result": {
# #                 "status":           validator_result.get("status", "unknown"),
# #                 "final_solution":   validator_result.get("solution", []),
# #                 "final_cost":       validator_result.get("final_cost", "N/A"),
# #                 "improvement_rate": validator_result.get("improvement_rate", 0),
# #                 "violations":       validator_result.get("violations", [])
# #             },
# #             "route_details":        validator_result.get("route_details", []),
# #             "knowledge_context":    rag_ctx.get("knowledge_summary", "暂无"),
# #             "algorithm_suggestion": rag_ctx.get("algorithm_suggestion", "暂无"),
# #             "conclusion": (
# #                 f"共 {len(solver_result.get('solution', []))} 辆车，"
# #                 f"状态：{validator_result.get('status')}，"
# #                 f"成本：{validator_result.get('final_cost')}，"
# #                 f"改进 {validator_result.get('improvement_rate', 0)}%。"
# #             )
# #         }

# # agents/knowledge_agent.py
# """
# KnowledgeAgent：CVRPTW 知识检索与报告生成 Agent（tool-free / 文件系统直读模式）

# 架构变化（相对旧版）：
#   - 移除了 KNOWLEDGE_TOOLS 和 _handle_tool_call()
#   - 不再向 LLM 注册 search_documents / web_search function tools
#   - retrieve_context()：
#       ① 系统本地运行 retrieve()（Chroma RAG）→ Observation A
#       ② 若本地结果 < 2 条 → 系统直接调 Firecrawl → Observation B
#       ③ 把 A + B 作为上下文注入 prompt，LLM 只输出 Phase 1 JSON
#   - generate_report()：
#       把 instance / solver_result / validator_result / retrieve JSON
#       + 可选 web 补充 注入 prompt，LLM 只输出 Phase 2 JSON
#   - answer_question()：新增，供 Orchestrator 直接路由"咨询类"问题
#       本地 RAG + 可选 web → LLM 输出自然语言回答

# 这种"系统先检索 / 执行 → 把结果注入 prompt → LLM 只负责推理输出"模式
# 即 SKILL.md 描述的"工具无关 / 文件系统直读模式"。
# """
# import json
# import os
# import sys
# from datetime import datetime
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# from agents.base_agent import BaseAgent, extract_json
# from skills.knowledge_report.knowledge_report import (
#     retrieve,
#     format_for_prompt,
#     save_json,
#     save_docx,
# )
# from typing import Dict, Any, List, Optional
# from dotenv import load_dotenv

# load_dotenv()

# try:
#     from firecrawl import Firecrawl
#     firecrawl = Firecrawl(api_key="fc-03d3d69dc25f48b2abbbc284c5b28d27")
# except ImportError:
#     firecrawl = None


# # ── Firecrawl 工具函数（系统直接调用，不经过 LLM tool_calls）──────────────────

# def _web_search(query: str, num_results: int = 3) -> str:
#     """
#     系统层直接调用 Firecrawl 搜索。
#     返回格式化文本供注入 prompt；失败时返回空字符串。
#     """
#     if not firecrawl:
#         return ""
#     try:
#         response = firecrawl.search(query=query, limit=num_results)
#         items = (
#             getattr(response, "web",  None)
#             or getattr(response, "data", None)
#             or (response if isinstance(response, list) else [])
#         )
#         if not items:
#             return ""
#         parts = []
#         for item in items:
#             if isinstance(item, dict):
#                 t = item.get("title", "无标题")
#                 u = item.get("url", "")
#                 c = item.get("markdown") or item.get("description") or ""
#             else:
#                 t = getattr(item, "title",    "无标题")
#                 u = getattr(item, "url",      "")
#                 c = getattr(item, "markdown", None) or getattr(item, "description", "")
#             parts.append(
#                 f"【{t}】\n链接: {u}\n{c[:600]}{'...' if len(c) > 600 else ''}"
#             )
#         return "\n\n---\n\n".join(parts)
#     except Exception as e:
#         print(f"  [KnowledgeAgent] Firecrawl 搜索失败: {e}")
#         return ""


# class KnowledgeAgent(BaseAgent):

#     def __init__(self, api_key: str, output_dir: str = "output"):
#         # BaseAgent 读取完整 SKILL.md 作为 system prompt，self.tools 默认为 []
#         super().__init__(api_key, skill_name="knowledge_report")
#         self.output_dir            = output_dir
#         self._cached_knowledge: Optional[Dict] = None

#     # ── Phase 1：知识检索（retrieve）─────────────────────────────────────────

#     def retrieve_context(self, instance: Dict[str, Any]) -> Dict[str, Any]:
#         """
#         tool-free 检索流程：
#           1. 系统本地运行 Chroma RAG → Observation A
#           2. 若有效结果 < 2 → 系统调 Firecrawl → Observation B
#           3. 把 A + B 注入 prompt，LLM 输出 Phase 1 retrieve JSON
#         """
#         n = len(instance.get("customers", []))
#         print(f"  [KnowledgeAgent/retrieve] 开始检索，规模: {n} 个客户")

#         # ── Observation A：本地 RAG ────────────────────────────────────────────
#         query    = f"CVRPTW {n} customers time window vehicle routing capacity {instance.get('capacity')}"
#         docs     = retrieve(query, top_k=5)
#         rag_text = format_for_prompt(docs) if docs else "（本地知识库暂无相关内容）"
#         web_used = False

#         print(f"  [KnowledgeAgent/retrieve] 本地 RAG 结果: {len(docs)} 条")

#         # ── Observation B：web search（本地结果不足时补充）────────────────────
#         web_text = ""
#         if len(docs) < 2:
#             print(f"  [KnowledgeAgent/retrieve] 本地结果 < 2，补充 web search...")
#             web_query = (
#                 f"CVRPTW {n} customers benchmark solution algorithm Solomon"
#             )
#             web_text = _web_search(web_query, num_results=3)
#             if web_text:
#                 web_used = True
#                 print(f"  [KnowledgeAgent/retrieve] web search 完成，长度: {len(web_text)} 字符")
#             else:
#                 print(f"  [KnowledgeAgent/retrieve] web search 无结果或未配置")

#         # ── 注入上下文，LLM 输出 Phase 1 JSON ─────────────────────────────────
#         context_section = f"## 本地知识库检索结果\n{rag_text}"
#         if web_text:
#             context_section += f"\n\n## 补充 Web 搜索结果\n{web_text}"

#         prompt = (
#             f"【Phase 1 — 知识检索】\n\n"
#             f"## 问题特征\n"
#             f"- 客户数：{n}\n"
#             f"- 容量：{instance.get('capacity')}\n"
#             f"- 实例摘要：{json.dumps(instance, ensure_ascii=False)[:300]}...\n\n"
#             f"{context_section}\n\n"
#             f"请综合以上检索结果，输出 Phase 1 retrieve JSON。"
#         )

#         raw    = self.run(prompt)
#         result = extract_json(raw)

#         if result:
#             result["_web_search_used"] = web_used
#             print(f"  [KnowledgeAgent/retrieve] 分类: {result.get('instance_classification', 'N/A')}")
#             self._cached_knowledge = result
#             return result

#         # LLM 解析失败 → 本地 fallback
#         fb = {
#             "phase":                   "retrieve",
#             "knowledge_summary":       rag_text if docs else "暂无相关知识",
#             "instance_classification": f"规模：{n} 个客户，容量：{instance.get('capacity')}",
#             "benchmark_reference":     None,
#             "algorithm_suggestion":    "建议使用最近邻启发式 + 2-opt 局部搜索",
#             "sources":                 [d["source"] for d in docs],
#             "_web_search_used":        web_used,
#         }
#         self._cached_knowledge = fb
#         return fb

#     # ── Phase 2：报告生成（report）────────────────────────────────────────────

#     def generate_report(
#         self,
#         instance:         Dict[str, Any],
#         solver_result:    Dict[str, Any],
#         validator_result: Dict[str, Any],
#         knowledge:        Optional[Dict[str, Any]] = None,
#     ) -> Dict[str, str]:
#         """
#         tool-free 报告生成：
#           把所有上下文注入 prompt，LLM 输出 Phase 2 report JSON，
#           再由系统调用 save_json / save_docx 落盘。
#         """
#         rag_ctx = knowledge or self._cached_knowledge or {}
#         print(f"  [KnowledgeAgent/report] 开始生成报告...")

#         # retrieve 阶段未做 web search 时，此处补充一次以丰富报告背景
#         web_supplement = ""
#         if not rag_ctx.get("_web_search_used", False):
#             n              = len(instance.get("customers", []))
#             classification = rag_ctx.get("instance_classification", "CVRPTW")
#             search_query   = f"CVRPTW {n} customers solution benchmark {classification}"
#             print(f"  [KnowledgeAgent/report] 补充 web search: '{search_query}'")
#             web_text = _web_search(search_query, num_results=2)
#             if web_text:
#                 web_supplement = f"\n\n## 补充 Web 搜索结果（报告阶段）\n{web_text}"
#                 print(f"  [KnowledgeAgent/report] 补充搜索完成，长度: {len(web_text)} 字符")
#             else:
#                 print(f"  [KnowledgeAgent/report] 补充搜索无结果或未配置，跳过")

#         prompt = (
#             f"【Phase 2 — 生成分析报告】\n\n"
#             f"## 问题实例\n```json\n{json.dumps(instance, ensure_ascii=False, indent=2)}\n```\n\n"
#             f"## 初始解（Solver Phase 1）\n```json\n{json.dumps(solver_result, ensure_ascii=False, indent=2)}\n```\n\n"
#             f"## 验证优化结果（Solver Phase 2）\n```json\n{json.dumps(validator_result, ensure_ascii=False, indent=2)}\n```\n\n"
#             f"## 知识检索结果（Retrieve Phase）\n```json\n{json.dumps(rag_ctx, ensure_ascii=False, indent=2)}\n```"
#             f"{web_supplement}\n\n"
#             f"请综合以上所有信息，输出 Phase 2 report JSON。"
#         )

#         raw         = self.run(prompt)
#         report_data = extract_json(raw) or self._build_fallback_report(
#             instance, solver_result, validator_result, rag_ctx
#         )
#         report_data["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#         os.makedirs(self.output_dir, exist_ok=True)
#         json_path = save_json(report_data, self.output_dir)
#         print(f"  [KnowledgeAgent/report] JSON: {json_path}")

#         docx_path = None
#         try:
#             docx_path = save_docx(report_data, self.output_dir)
#             print(f"  [KnowledgeAgent/report] DOCX: {docx_path}")
#         except Exception as e:
#             print(f"  [KnowledgeAgent/report] DOCX 生成失败: {e}")

#         return {"json_path": json_path, "docx_path": docx_path, "report_data": report_data}

#     # ── 直接问答（answer_question）────────────────────────────────────────────

#     def answer_question(self, question: str) -> Dict[str, Any]:
#         """
#         供 Orchestrator 路由"咨询类"问题（knowledge_report skill）：
#           1. 本地 RAG 检索问题相关内容
#           2. 若结果 < 2 → 补充 web search
#           3. 把检索内容注入 prompt，LLM 输出自然语言回答
#         返回 {"answer": str, "sources": [...], "_web_search_used": bool}
#         """
#         print(f"  [KnowledgeAgent/QA] 问题: {question[:80]}...")

#         # 本地 RAG
#         docs     = retrieve(question, top_k=5)
#         rag_text = format_for_prompt(docs) if docs else "（本地知识库暂无相关内容）"
#         web_used = False

#         # 结果不足时 web search
#         web_text = ""
#         if len(docs) < 2:
#             web_text = _web_search(question, num_results=3)
#             if web_text:
#                 web_used = True

#         # 构建上下文
#         context = f"## 本地知识库\n{rag_text}"
#         if web_text:
#             context += f"\n\n## Web 搜索补充\n{web_text}"

#         prompt = (
#             f"请根据以下检索内容，用中文回答用户的问题。\n\n"
#             f"## 用户问题\n{question}\n\n"
#             f"{context}\n\n"
#             f"直接给出清晰、准确的回答（无需输出 JSON）。"
#         )

#         answer  = self.run(prompt)
#         sources = [d.get("source", "") for d in docs]

#         return {
#             "answer":          answer,
#             "sources":         sources,
#             "_web_search_used": web_used,
#         }

#     # ── Fallback 报告 ─────────────────────────────────────────────────────────

#     def _build_fallback_report(
#         self,
#         instance:         Dict[str, Any],
#         solver_result:    Dict[str, Any],
#         validator_result: Dict[str, Any],
#         rag_ctx:          Dict[str, Any],
#     ) -> Dict[str, Any]:
#         return {
#             "phase": "report",
#             "title": "CVRPTW 求解分析报告",
#             "problem_summary": {
#                 "num_customers":    len(instance.get("customers", [])),
#                 "vehicle_capacity": instance.get("capacity", "N/A"),
#                 "instance_type":    rag_ctx.get("instance_classification", "未分类"),
#             },
#             "solving_process": {
#                 "reasoning":        solver_result.get("reasoning", "N/A"),
#                 "initial_solution": solver_result.get("solution", []),
#                 "initial_cost":     validator_result.get("original_cost", "N/A"),
#             },
#             "validation_result": {
#                 "status":           validator_result.get("status", "unknown"),
#                 "final_solution":   validator_result.get("solution", []),
#                 "final_cost":       validator_result.get("final_cost", "N/A"),
#                 "improvement_rate": validator_result.get("improvement_rate", 0),
#                 "violations":       validator_result.get("violations", []),
#             },
#             "route_details":        validator_result.get("route_details", []),
#             "knowledge_context":    rag_ctx.get("knowledge_summary", "暂无"),
#             "algorithm_suggestion": rag_ctx.get("algorithm_suggestion", "暂无"),
#             "conclusion": (
#                 f"共 {len(validator_result.get('solution', []))} 辆车，"
#                 f"状态：{validator_result.get('status')}，"
#                 f"成本：{validator_result.get('final_cost')}，"
#                 f"改进 {validator_result.get('improvement_rate', 0)}%。"
#             ),
#         }

# agents/knowledge_agent.py
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv

from agents.base_agent import BaseAgent, extract_json
from skills.knowledge_report.knowledge_report import (
    retrieve,
    format_for_prompt,
    save_json,
    save_docx,
)

load_dotenv()

try:
    from firecrawl import Firecrawl
    firecrawl = Firecrawl(api_key="fc-03d3d69dc25f48b2abbbc284c5b28d27")
except ImportError:
    firecrawl = None


def _firecrawl_search(query: str, limit: int = 3) -> List[Dict[str, str]]:
    if not _firecrawl:
        return []
    try:
        resp = _firecrawl.search(query=query, limit=limit)
        items = (getattr(resp, 'web', None) or getattr(resp, 'data', None) or (resp if isinstance(resp, list) else []))
        out = []
        for it in items or []:
            if isinstance(it, dict):
                out.append({
                    'title': it.get('title', '无标题'),
                    'url': it.get('url', ''),
                    'snippet': (it.get('markdown') or it.get('description') or '')[:800],
                })
            else:
                out.append({
                    'title': getattr(it, 'title', '无标题'),
                    'url': getattr(it, 'url', ''),
                    'snippet': (getattr(it, 'markdown', None) or getattr(it, 'description', '') or '')[:800],
                })
        return out
    except Exception:
        return []


class KnowledgeAgent(BaseAgent):
    """Tool-free KnowledgeAgent.

    Runtime does:
    - local RAG retrieve via Chroma (skills/knowledge_report/knowledge_report.py)
    - optional web supplement via Firecrawl when local results are insufficient
    - LLM synthesizes either retrieve JSON (phase 1) or report JSON (phase 2)
    """

    def __init__(self, api_key: str, output_dir: str = 'output'):
        super().__init__(api_key, skill_name='knowledge_report')
        self.output_dir = output_dir
        self._cached_knowledge: Optional[Dict[str, Any]] = None

    def dispatch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generic entrypoint for Orchestrator dynamic dispatch.

        Supports either:
          - payload.question / payload.query -> answer_question
          - payload.instance -> retrieve_context (if instance is a dict)
        """
        if not isinstance(payload, dict):
            return {'error': 'payload must be a dict'}
        q = payload.get('question') or payload.get('query')
        if isinstance(q, str) and q.strip():
            return self.answer_question(q.strip())
        inst = payload.get('instance')
        if isinstance(inst, dict):
            return self.retrieve_context(inst)
        return {'error': 'knowledge_report expects payload.question (string) or payload.instance (dict)'}

    def try_parse_instance(self, text: str) -> Optional[Dict[str, Any]]:
        """Best-effort parse an instance JSON object from arbitrary text."""
        if not text:
            return None
        parsed = extract_json(text)
        if isinstance(parsed, dict) and ('customers' in parsed and 'depot' in parsed):
            return parsed
        return None

    def retrieve_context(self, instance: Dict[str, Any]) -> Dict[str, Any]:
        n = len(instance.get('customers', []))
        cap = instance.get('capacity')
        print(f"  [KnowledgeAgent/retrieve] local RAG | customers={n} | cap={cap}")

        # 1) local RAG
        query = f"CVRPTW {n} customers capacity {cap} time window benchmark algorithm"
        docs = retrieve(query, top_k=5)
        local_ctx = format_for_prompt(docs) if docs else ''
        sources = [d.get('source', '') for d in (docs or []) if d.get('source')]

        # 2) optional web supplement if too few docs
        web_used = False
        web_ctx = ''
        web_sources: List[str] = []
        if len(docs or []) < 2:
            web_used = True
            web_items = _firecrawl_search(query, limit=3)
            if web_items:
                parts = []
                for it in web_items:
                    parts.append(f"【{it['title']}】\n{it['url']}\n{it['snippet']}")
                    if it.get('url'):
                        web_sources.append(it['url'])
                web_ctx = "\n\n---\n\n".join(parts)

        # Ask LLM to produce retrieve JSON
        prompt = (
            "【Phase 1 — 知识检索】\n\n"
            f"实例摘要：\n```json\n{json.dumps(instance, ensure_ascii=False, indent=2)}\n```\n\n"
            f"本地检索片段：\n{local_ctx or '（无）'}\n\n"
        )
        if web_ctx:
            prompt += f"补充 Web 搜索片段：\n{web_ctx}\n\n"
        prompt += "请综合以上上下文，输出 Phase 1 JSON。"

        raw = self.run(prompt)
        result = extract_json(raw)

        if not isinstance(result, dict):
            # fallback
            result = {
                'phase': 'retrieve',
                'knowledge_summary': (local_ctx[:800] if local_ctx else '暂无相关知识'),
                'instance_classification': f"规模：{n} 客户；容量：{cap}",
                'benchmark_reference': None,
                'algorithm_suggestion': '建议：最近邻启发式 + 2-opt；规模较大可考虑 LNS/ALNS。',
                'sources': sources + web_sources,
            }

        # attach internal flags
        result['_web_search_used'] = web_used and bool(web_ctx)
        if 'sources' not in result or not isinstance(result['sources'], list):
            result['sources'] = sources + web_sources

        self._cached_knowledge = result
        return result

    def answer_question(self, question: str) -> Dict[str, Any]:
        question = (question or '').strip()
        if not question:
            return {'answer': '请提供问题。', 'sources': []}

        # local retrieve
        docs = retrieve(question, top_k=5)
        local_ctx = format_for_prompt(docs) if docs else ''
        sources = [d.get('source', '') for d in (docs or []) if d.get('source')]

        web_sources: List[str] = []
        web_ctx = ''
        if len(docs or []) < 2:
            web_items = _firecrawl_search(question, limit=3)
            if web_items:
                parts = []
                for it in web_items:
                    parts.append(f"【{it['title']}】\n{it['url']}\n{it['snippet']}")
                    if it.get('url'):
                        web_sources.append(it['url'])
                web_ctx = "\n\n---\n\n".join(parts)

        prompt = (
            "你是 CVRPTW 领域助手。基于给定上下文回答问题，尽量给出可操作建议，并在末尾列出你使用的来源（用项目符号）。\n\n"
            f"问题：{question}\n\n"
            f"本地知识库片段：\n{local_ctx or '（无）'}\n\n"
        )
        if web_ctx:
            prompt += f"补充 Web 搜索片段：\n{web_ctx}\n\n"
        prompt += "请输出答案（自然语言）。"

        answer = self.run(prompt)
        return {'answer': answer, 'sources': [s for s in (sources + web_sources) if s]}

    def generate_report(
        self,
        instance: Dict[str, Any],
        solver_result: Dict[str, Any],
        validator_result: Dict[str, Any],
        knowledge: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rag_ctx = knowledge or self._cached_knowledge or {}
        print('  [KnowledgeAgent/report] generating report')

        prompt = (
            "【Phase 2 — 生成分析报告】\n\n"
            f"## 问题实例\n```json\n{json.dumps(instance, ensure_ascii=False, indent=2)}\n```\n\n"
            f"## 初始解（Solver Phase 1）\n```json\n{json.dumps(solver_result, ensure_ascii=False, indent=2)}\n```\n\n"
            f"## 验证优化结果（Solver Phase 2）\n```json\n{json.dumps(validator_result, ensure_ascii=False, indent=2)}\n```\n\n"
            f"## 知识检索结果（Retrieve Phase）\n```json\n{json.dumps(rag_ctx, ensure_ascii=False, indent=2)}\n```\n\n"
            "请综合以上信息，输出 Phase 2 JSON 报告。"
        )

        raw = self.run(prompt)
        report_data = extract_json(raw)
        if not isinstance(report_data, dict):
            report_data = self._build_fallback_report(instance, solver_result, validator_result, rag_ctx)

        report_data['generated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        os.makedirs(self.output_dir, exist_ok=True)
        json_path = save_json(report_data, self.output_dir)
        docx_path = None
        try:
            docx_path = save_docx(report_data, self.output_dir)
        except Exception:
            docx_path = None

        return {'json_path': json_path, 'docx_path': docx_path, 'report_data': report_data}

    def _build_fallback_report(self, instance, solver_result, validator_result, rag_ctx) -> Dict[str, Any]:
        return {
            'phase': 'report',
            'title': 'CVRPTW 求解分析报告',
            'problem_summary': {
                'num_customers': len(instance.get('customers', [])),
                'vehicle_capacity': instance.get('capacity', 'N/A'),
                'instance_type': rag_ctx.get('instance_classification', '未分类'),
            },
            'solving_process': {
                'reasoning': solver_result.get('reasoning', 'N/A'),
                'initial_solution': solver_result.get('solution', []),
                'initial_cost': validator_result.get('original_cost', 'N/A'),
            },
            'validation_result': {
                'status': validator_result.get('status', 'unknown'),
                'final_solution': validator_result.get('solution', []),
                'final_cost': validator_result.get('final_cost', 'N/A'),
                'improvement_rate': validator_result.get('improvement_rate', 0),
                'violations': validator_result.get('violations', []),
            },
            'route_details': validator_result.get('route_details', []),
            'knowledge_context': rag_ctx.get('knowledge_summary', '暂无'),
            'algorithm_suggestion': rag_ctx.get('algorithm_suggestion', '暂无'),
            'conclusion': (
                f"共 {len(validator_result.get('solution', []))} 辆车，"
                f"状态：{validator_result.get('status')}，"
                f"成本：{validator_result.get('final_cost')}。"
            ),
        }
