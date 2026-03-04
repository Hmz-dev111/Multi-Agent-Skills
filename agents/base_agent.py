# # # agents/base_agent.py
# # import os
# # import json
# # import re
# # import yaml
# # from openai import OpenAI
# # from typing import List, Dict, Any, Optional

# # KIMI_BASE_URL = "https://api.moonshot.cn/v1"
# # MODEL         = "kimi-k2.5"
# # SKILLS_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'skills'))
# # PROJECT_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


# # def load_all_skills() -> Dict[str, Dict]:
# #     """扫描 skills/ 子文件夹，读取每个 skill.yaml，返回 {skill_name: yaml_dict}"""
# #     skills = {}
# #     for entry in os.scandir(SKILLS_DIR):
# #         if not entry.is_dir():
# #             continue
# #         yaml_path = os.path.join(entry.path, 'skill.yaml')
# #         if not os.path.exists(yaml_path):
# #             continue
# #         with open(yaml_path, 'r', encoding='utf-8') as f:
# #             meta = yaml.safe_load(f)
# #         skills[meta['name']] = meta
# #     return skills


# # def load_skill_prompt(skill_name: str) -> str:
# #     """
# #     组合 skill system prompt：
# #       yaml.description（角色背景） + yaml.tools（工具权限） + skill.md（详细指令）
# #     """
# #     yaml_path = os.path.join(SKILLS_DIR, skill_name, 'skill.yaml')
# #     if not os.path.exists(yaml_path):
# #         raise FileNotFoundError(f"Skill YAML not found: {yaml_path}")
# #     with open(yaml_path, 'r', encoding='utf-8') as f:
# #         meta = yaml.safe_load(f)

# #     ref     = meta.get('reference', f"skills/{skill_name}/reference.md")
# #     md_path = os.path.join(PROJECT_ROOT, ref)
# #     if not os.path.exists(md_path):
# #         raise FileNotFoundError(f"Skill MD not found: {md_path}")
# #     with open(md_path, 'r', encoding='utf-8') as f:
# #         md_content = f.read()

# #     return (
# #         f"## 技能定位\n{meta.get('description', '').strip()}\n\n"
# #         f"## 可用工具\n{', '.join(meta.get('tools', [])) or '无'}\n\n"
# #         f"---\n\n"
# #         f"{md_content}"
# #     )


# # def build_skills_catalog(skills: Dict[str, Dict]) -> str:
# #     """将所有 skills 元数据格式化为供 Orchestrator 使用的目录字符串"""
# #     lines = ["## 已注册技能目录\n"]
# #     for name, meta in skills.items():
# #         lines.append(f"### {name}")
# #         lines.append(f"描述：{meta.get('description', '').strip()}")
# #         lines.append(f"触发关键词：{', '.join(meta.get('triggers', []))}")
# #         lines.append(f"输入：{[i['name'] for i in meta.get('inputs', [])]}")
# #         lines.append(f"输出：{[o['name'] for o in meta.get('outputs', [])]}")
# #         lines.append("")
# #     return "\n".join(lines)


# # def extract_json(text: str) -> Optional[Dict]:
# #     cleaned = re.sub(r"```json\s*", "", text)
# #     cleaned = re.sub(r"```\s*", "", cleaned).strip()
# #     try:
# #         return json.loads(cleaned)
# #     except Exception:
# #         match = re.search(r"\{.*\}", cleaned, re.DOTALL)
# #         if match:
# #             try:
# #                 return json.loads(match.group())
# #             except Exception:
# #                 pass
# #     return None


# # class BaseAgent:
# #     def __init__(self, api_key: str, skill_name: str):
# #         self.client        = OpenAI(api_key=api_key, base_url=KIMI_BASE_URL)
# #         self.skill_name    = skill_name
# #         self.system_prompt = load_skill_prompt(skill_name)
# #         self.tools: List[Dict] = []

# #     def _handle_tool_call(self, name: str, args: Dict[str, Any]) -> str:
# #         return f"工具 {name} 未实现"

# #     def run(self, user_message: str, max_steps: int = 10) -> str:
# #         messages = [
# #             {"role": "system", "content": self.system_prompt},
# #             {"role": "user",   "content": user_message}
# #         ]
# #         for _ in range(max_steps):
# #             kwargs = dict(model=MODEL, messages=messages)
# #             if self.tools:
# #                 kwargs["tools"]       = self.tools
# #                 kwargs["tool_choice"] = "auto"
# #             resp   = self.client.chat.completions.create(**kwargs)
# #             msg    = resp.choices[0].message
# #             reason = resp.choices[0].finish_reason
# #             messages.append(msg.model_dump(exclude_unset=False))
# #             if reason == "stop" or not msg.tool_calls:
# #                 return msg.content or ""
# #             tool_results = []
# #             for tc in msg.tool_calls:
# #                 result_text = self._handle_tool_call(tc.function.name, json.loads(tc.function.arguments))
# #                 tool_results.append({"role": "tool", "tool_call_id": tc.id, "content": result_text})
# #             messages.extend(tool_results)
# #         for m in reversed(messages):
# #             if isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
# #                 return m["content"]
# #         return "Agent 超出最大步骤数"

# # agents/base_agent.py
# """
# BaseAgent：技能感知的基础 Agent 类（文件系统直读模式）

# 核心设计：
#   - 启动时 discover_skills() 扫描 skills/*/SKILL.md，**只解析 YAML frontmatter**
#     → 生成轻量 catalog 注入 Orchestrator system prompt
#   - 运行时 load_skill_prompt() **按需读取完整 SKILL.md**（frontmatter + 正文）
#     → 作为 Agent system prompt（lazy load）
#   - SKILL.md 是唯一入口
#   - BaseAgent 默认不启用 function tools（tool-free 模式）
#     → Agent 子类通过"LLM 输出 JSON + 本地执行"完成 Observation→Action 循环

# 目录结构（每个 skill）：
#   skills/
#     <skill_name>/
#       SKILL.md          ← frontmatter（元数据）+ Markdown 正文（指令）
#       schema/
#         input.yaml      ← 输入 schema（供 Orchestrator 动态生成 dispatch 模板）
#         output.yaml     ← 输出 schema（文档/校验用）
#       <skill_name>.py   ← 代码实现（供 Agent 直接 import）
# """
# import os
# import re
# import json
# import yaml
# from openai import OpenAI
# from typing import List, Dict, Any, Optional

# KIMI_BASE_URL = "https://api.moonshot.cn/v1"
# MODEL         = "kimi-k2.5"
# SKILLS_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'skills'))

# _FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)


# # ── SKILL.md 解析 ─────────────────────────────────────────────────────────────

# def _parse_skill_frontmatter(skill_md_text: str) -> Dict[str, Any]:
#     """
#     从 SKILL.md 文本中解析 YAML frontmatter。
#     只读 --- ... --- 之间的内容，不加载正文（保持 discover 阶段轻量）。
#     """
#     m = _FRONTMATTER_RE.match(skill_md_text)
#     if not m:
#         return {}
#     return yaml.safe_load(m.group(1)) or {}


# def _load_skill_schema(skill_name: str, schema_type: str) -> Optional[Dict]:
#     """
#     按需加载 skills/<skill_name>/schema/<schema_type>.yaml。
#     schema_type: 'input' 或 'output'
#     找不到文件时静默返回 None。
#     """
#     schema_path = os.path.join(SKILLS_DIR, skill_name, 'schema', f'{schema_type}.yaml')
#     if not os.path.exists(schema_path):
#         return None
#     with open(schema_path, 'r', encoding='utf-8') as f:
#         return yaml.safe_load(f)


# # ── 技能发现（启动时：只读 frontmatter）────────────────────────────────────────

# def discover_skills() -> Dict[str, Dict[str, Any]]:
#     """
#     启动时扫描 skills/*/SKILL.md，只解析 YAML frontmatter（name / description /
#     triggers / input_key / schema_paths 等元数据），不加载正文。
#     返回 {skill_name: meta}，meta 中附带 '_path' 指向 SKILL.md 路径。
#     """
#     skills: Dict[str, Dict[str, Any]] = {}
#     if not os.path.isdir(SKILLS_DIR):
#         return skills

#     for entry in os.scandir(SKILLS_DIR):
#         if not entry.is_dir():
#             continue
#         skill_md_path = os.path.join(entry.path, 'SKILL.md')
#         if not os.path.exists(skill_md_path):
#             continue
#         try:
#             text = open(skill_md_path, 'r', encoding='utf-8').read()
#             meta = _parse_skill_frontmatter(text)
#             name = meta.get('name') or entry.name
#             meta['_path'] = skill_md_path
#             skills[name]  = meta
#         except Exception as e:
#             print(f"[WARNING] 跳过技能 {entry.name}，frontmatter 解析失败: {e}")

#     return skills


# # 向后兼容别名（旧代码用 load_all_skills 的地方无需改动）
# load_all_skills = discover_skills


# # ── 技能加载（运行时：按需读取完整 SKILL.md）──────────────────────────────────

# def load_skill_prompt(skill_name: str) -> str:
#     """
#     按需加载完整 SKILL.md（frontmatter + Markdown 正文），直接作为 system prompt。
#     符合"文件系统直读"集成方式：SKILL.md 就是 Agent 的完整角色定义。
#     """
#     skill_md = os.path.join(SKILLS_DIR, skill_name, 'SKILL.md')
#     if not os.path.exists(skill_md):
#         raise FileNotFoundError(f"SKILL.md not found: {skill_md}")
#     return open(skill_md, 'r', encoding='utf-8').read()


# # ── 技能目录构建（注入 Orchestrator system prompt）──────────────────────────────

# def build_skills_catalog(skills: Dict[str, Dict[str, Any]]) -> str:
#     """
#     只用 frontmatter 生成 catalog 文本，注入 Orchestrator system prompt。
#     包含：description / triggers / input_key / 输入字段摘要。
#     """
#     lines = ["## Available Skills (discovered from skills/*/SKILL.md)\n"]

#     for name, meta in skills.items():
#         desc      = (meta.get('description') or '').strip()
#         triggers  = meta.get('triggers') or []
#         input_key = meta.get('input_key', '')

#         # 尝试从 schema/input.yaml 提取关键字段名，给 Orchestrator 提示
#         input_schema = _load_skill_schema(name, 'input')
#         field_hints  = ''
#         if input_schema and 'properties' in input_schema:
#             required = input_schema.get('required', [])
#             fields   = [
#                 f"{k}{'*' if k in required else ''}"
#                 for k in input_schema['properties']
#             ]
#             field_hints = f"（字段：{', '.join(fields)}，*=必填）"

#         lines.append(f"### {name}")
#         lines.append(f"- description: {desc}")
#         lines.append(f"- triggers: {', '.join(triggers) if triggers else '(none)'}")
#         if input_key:
#             lines.append(f"- input_key: {input_key}  {field_hints}")
#         lines.append("")

#     return "\n".join(lines)


# # ── JSON 提取工具 ─────────────────────────────────────────────────────────────

# def extract_json(text: str) -> Optional[Dict]:
#     """从 LLM 输出中提取 JSON，兼容 ```json...``` 包裹和裸 JSON 两种格式"""
#     cleaned = re.sub(r'```json\s*', '', text)
#     cleaned = re.sub(r'```\s*', '', cleaned).strip()
#     try:
#         return json.loads(cleaned)
#     except Exception:
#         match = re.search(r'\{.*\}', cleaned, re.DOTALL)
#         if match:
#             try:
#                 return json.loads(match.group())
#             except Exception:
#                 pass
#     return None


# # ── BaseAgent ─────────────────────────────────────────────────────────────────

# class BaseAgent:
#     """
#     所有 Agent 的基类。

#     默认工作模式（tool-free / 文件系统直读）：
#       - self.tools = []：不向 LLM 注册任何 function tools
#       - Agent 子类通过"LLM 输出结构化 JSON → 本地代码执行 → 把 Observation
#         写回 prompt → 再次调用 LLM"完成 Action-Observation 循环
#       - system prompt 直接来自完整 SKILL.md（frontmatter + 正文）

#     如果子类确实需要 function tools，可在 __init__ 中设置 self.tools。
#     """

#     def __init__(self, api_key: str, skill_name: str):
#         self.client        = OpenAI(api_key=api_key, base_url=KIMI_BASE_URL)
#         self.skill_name    = skill_name
#         self.system_prompt = load_skill_prompt(skill_name)
#         self.tools: List[Dict] = []   # 默认 tool-free；子类可覆盖

#     def _handle_tool_call(self, name: str, args: Dict[str, Any]) -> str:
#         """子类覆盖此方法以支持 function tools（非 tool-free 模式时使用）"""
#         return f"工具 {name} 未实现"

#     def run(self, user_message: str, max_steps: int = 10) -> str:
#         """
#         运行 Agent：循环调用 LLM，直到 finish_reason == 'stop' 或超出步骤数。
#         tool-free 模式下 LLM 直接输出结构化 JSON，不会触发 tool_calls。
#         """
#         messages: List[Dict] = [
#             {"role": "system", "content": self.system_prompt},
#             {"role": "user",   "content": user_message},
#         ]

#         for _ in range(max_steps):
#             kwargs: Dict[str, Any] = {"model": MODEL, "messages": messages}
#             if self.tools:
#                 kwargs["tools"]       = self.tools
#                 kwargs["tool_choice"] = "auto"

#             resp   = self.client.chat.completions.create(**kwargs)
#             choice = resp.choices[0]
#             msg    = choice.message
#             reason = choice.finish_reason

#             # 手动构造 assistant 消息（避免 model_dump 引入 null 字段导致 API 报错）
#             assistant_msg: Dict[str, Any] = {"role": "assistant"}
#             if msg.content:
#                 assistant_msg["content"] = msg.content
#             if msg.tool_calls:
#                 assistant_msg["tool_calls"] = [
#                     {
#                         "id":       tc.id,
#                         "type":     "function",
#                         "function": {
#                             "name":      tc.function.name,
#                             "arguments": tc.function.arguments,
#                         },
#                     }
#                     for tc in msg.tool_calls
#                 ]
#             messages.append(assistant_msg)

#             # 停止条件：stop 或无 tool_calls（tool-free 模式正常结束路径）
#             if reason == "stop" or not msg.tool_calls:
#                 return msg.content or ""

#             # 处理 function tool 调用（仅在 self.tools 非空时可能触发）
#             for tc in msg.tool_calls:
#                 try:
#                     args = json.loads(tc.function.arguments)
#                 except json.JSONDecodeError:
#                     args = {}
#                 result_text = self._handle_tool_call(tc.function.name, args)
#                 messages.append({
#                     "role":         "tool",
#                     "tool_call_id": tc.id,
#                     "content":      result_text,
#                 })

#         # 超出步骤数：返回最后一条 assistant 内容
#         for m in reversed(messages):
#             if isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
#                 return m["content"]
#         return "Agent 超出最大步骤数"

# agents/base_agent.py
import os
import json
import re
from typing import List, Dict, Any, Optional

import yaml
from openai import OpenAI

# Kimi
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
MODEL = "kimi-k2.5"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SKILLS_DIR = os.path.join(PROJECT_ROOT, 'skills')

# Cache discovered metadata so prompt loading can map skill name -> folder path
_SKILL_META_CACHE: Optional[Dict[str, Dict[str, Any]]] = None

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> Dict[str, Any]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    data = yaml.safe_load(m.group(1))
    return data or {}


def discover_skills() -> Dict[str, Dict[str, Any]]:
    """Scan skills/*/SKILL.md and return {skill_name: metadata}.

    Startup discovery should only read YAML frontmatter (name/description/triggers/schema),
    keeping the system prompt lightweight.
    """
    skills: Dict[str, Dict[str, Any]] = {}
    if not os.path.isdir(SKILLS_DIR):
        return skills

    for entry in os.scandir(SKILLS_DIR):
        if not entry.is_dir():
            continue
        skill_md = os.path.join(entry.path, 'SKILL.md')
        if not os.path.exists(skill_md):
            continue
        with open(skill_md, 'r', encoding='utf-8') as f:
            text = f.read()
        meta = _parse_frontmatter(text)
        name = meta.get('name') or entry.name
        meta['_path'] = skill_md
        meta['_dir'] = entry.path
        skills[name] = meta
    global _SKILL_META_CACHE
    _SKILL_META_CACHE = skills
    return skills


# Backwards-compat alias (older orchestrator imports load_all_skills)
def load_all_skills() -> Dict[str, Dict[str, Any]]:
    return discover_skills()


def load_skill_prompt(skill_name: str) -> str:
    """Lazy-load full SKILL.md content for a given skill.

    Note: skill folder name may differ from frontmatter 'name'. We therefore
    resolve by scanning skills/ if needed.
    """
    global _SKILL_META_CACHE
    if _SKILL_META_CACHE is None:
        _SKILL_META_CACHE = discover_skills()

    meta = _SKILL_META_CACHE.get(skill_name)
    if meta and meta.get('_path') and os.path.exists(meta['_path']):
        with open(meta['_path'], 'r', encoding='utf-8') as f:
            return f.read()

    # fallback: try folder name == skill_name
    skill_md = os.path.join(SKILLS_DIR, skill_name, 'SKILL.md')
    if os.path.exists(skill_md):
        with open(skill_md, 'r', encoding='utf-8') as f:
            return f.read()

    raise FileNotFoundError(f"SKILL.md not found for skill '{skill_name}' under {SKILLS_DIR}")


def build_skills_catalog(skills: Dict[str, Dict[str, Any]]) -> str:
    """Format a compact catalog for Orchestrator system prompt."""
    lines = ["## Available Skills (discovered from skills/*/SKILL.md)\n"]
    for name, meta in skills.items():
        desc = (meta.get('description') or '').strip()
        triggers = meta.get('triggers') or []
        input_key = meta.get('input_key') or 'input'
        lines.append(f"### {name}")
        if desc:
            lines.append(f"- description: {desc}")
        lines.append(f"- triggers: {', '.join(triggers) if triggers else '(none)'}")
        lines.append(f"- input_key: {input_key}")
        if meta.get('schema_paths'):
            sp = meta['schema_paths']
            lines.append(f"- schema_paths: input={sp.get('input','')}, output={sp.get('output','')}")
        elif meta.get('inputs_schema'):
            # inline schema (optional)
            req = (meta.get('inputs_schema') or {}).get('required') or []
            lines.append(f"- required_fields: {', '.join(req) if req else '(none)'}")
        lines.append("")
    return "\n".join(lines)


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    cleaned = re.sub(r"```json\s*", "", text)
    cleaned = re.sub(r"```\s*", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                return None
    return None


class BaseAgent:
    """Base LLM agent that loads instructions from SKILL.md.

    This project uses filesystem-read skills: the agent reads SKILL.md directly.
    """

    def __init__(self, api_key: str, skill_name: str, base_url: str = KIMI_BASE_URL, model: str = MODEL):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.skill_name = skill_name
        self.system_prompt = load_skill_prompt(skill_name)
        self.tools: List[Dict[str, Any]] = []  # intentionally empty for tool-free skill flow

    def run(self, user_message: str, max_steps: int = 6) -> str:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        # tool-free by default; still supports tools if some agent opts-in later
        for _ in range(max_steps):
            kwargs: Dict[str, Any] = {"model": self.model, "messages": messages}
            if self.tools:
                kwargs["tools"] = self.tools
                kwargs["tool_choice"] = "auto"

            resp = self.client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_unset=False))

            # Stop if no tool call is requested
            if not getattr(msg, 'tool_calls', None):
                return msg.content or ""

            # If tools exist and were called, agent subclasses may override this handling.
            # Here we fail fast with a readable error.
            return "Tool calls are disabled in filesystem-read skills mode."

        # fallback
        for m in reversed(messages):
            if isinstance(m, dict) and m.get('role') == 'assistant' and m.get('content'):
                return m['content']
        return "Agent exceeded max steps"
