import json
from ..config import get_provider_cfg
from .llm.provider import chat_once
from ..prompts.planner import PLANNER_SYSTEM

async def generate_plan(query: str, depth="standard", provider_cfg=None):
    cfg = provider_cfg or get_provider_cfg()
    if not cfg:
        # fallback mock plan
        return {
          "title": query[:60],
          "objective": f"Deep research on {query}",
          "sub_questions": [
            {"id":"Q1","question":f"What is {query} - core definition and facts?","rationale":"Establish baseline","queries":[query, f"{query} overview 2026"],"priority":"high"},
            {"id":"Q2","question":f"History and evolution of {query}","rationale":"Context","queries":[f"{query} history timeline", f"{query} evolution"],"priority":"medium"},
            {"id":"Q3","question":f"Key players, tools, and ecosystem around {query}","rationale":"Map landscape","queries":[f"{query} best tools 2026", f"{query} key players"],"priority":"high"},
            {"id":"Q4","question":f"Recent developments and controversies in {query} (2025-2026)","rationale":"Freshness","queries":[f"{query} news 2026", f"{query} controversy debate"],"priority":"high"},
            {"id":"Q5","question":f"Future outlook and predictions for {query}","rationale":"Forward view","queries":[f"{query} future trends 2026", f"{query} predictions"], "priority":"medium"},
          ],
          "strategy": "Breadth-first web search then deep dive per sub-question, prioritize primary sources.",
          "expected_sources": 15 if depth=="standard" else (8 if depth=="quick" else 25)
        }
    # depth mapping per UX: quick 3-4, standard 5-6, deep 7-8, deep_max 8-10 autonomous
    if depth == "quick": n = 4
    elif depth == "standard": n = 6
    elif depth == "deep": n = 8
    elif depth == "deep_max": n = 9
    else: n = 6
    user_prompt = f"Topic: {query}\nDepth: {depth} (expect {n} sub-questions, deep_max means autonomous until clear)\nGenerate the research plan JSON now. No extra text."
    try:
        raw = await chat_once(cfg, [{"role":"system","content":PLANNER_SYSTEM},{"role":"user","content":user_prompt}], temperature=0.6)
        # strip code fences
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        j = json.loads(raw.strip())
        return j
    except Exception as e:
        print("planner llm failed", e)
        # return fallback
        return await generate_plan(query, depth, provider_cfg=None)
