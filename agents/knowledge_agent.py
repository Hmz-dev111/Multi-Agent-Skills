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

_firecrawl = None
try:
    from firecrawl import Firecrawl  # type: ignore
    api_key = os.getenv('FIRECRAWL_API_KEY', '')
    if api_key:
        _firecrawl = Firecrawl(api_key=api_key)
except Exception:
    _firecrawl = None


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
    def __init__(self, api_key: str, output_dir: str = 'output'):
        super().__init__(api_key, skill_name='knowledge_report')
        self.output_dir = output_dir
        self._cached_knowledge: Optional[Dict[str, Any]] = None

    def dispatch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
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

        query = f"CVRPTW {n} customers capacity {cap} time window benchmark algorithm"
        docs = retrieve(query, top_k=5)
        local_ctx = format_for_prompt(docs) if docs else ''
        sources = [d.get('source', '') for d in (docs or []) if d.get('source')]

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

        # 第一步
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
