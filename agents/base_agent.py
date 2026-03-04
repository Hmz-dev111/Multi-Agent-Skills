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
