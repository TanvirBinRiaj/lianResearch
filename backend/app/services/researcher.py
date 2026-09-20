import asyncio, json, re
from urllib.parse import urlparse
from ..config import get_provider_cfg, load_config
from .llm.provider import chat_once
from ..prompts.planner import (
    SYNTHESIZER_SYSTEM, GAP_ANALYSIS_SYSTEM, EVIDENCE_SYSTEM, VERIFICATION_SYSTEM,
)
from .reach import search_and_fetch

# ---- per-depth budgets: every depth iterates, deeper ones go further ----
DEPTH_CFG = {
    "quick":    {"iters": 1, "queries": 2, "per_q": 6,  "cap": 15, "excerpt": 1500, "evidence": True},
    "standard": {"iters": 2, "queries": 2, "per_q": 8,  "cap": 28, "excerpt": 2200, "evidence": True},
    "deep":     {"iters": 3, "queries": 3, "per_q": 10, "cap": 35, "excerpt": 2500, "evidence": True},
    "deep_max": {"iters": 4, "queries": 4, "per_q": 12, "cap": 45, "excerpt": 2500, "evidence": True},
}
GLOBAL_PROMPT_CAP = 32000  # chars of source text fed to the synthesizer
STOP_COVERAGE = 80

# ---- source authority tiers (soft rank signal, never a filter) ----
_TIER1_HINTS = (
    ".gov", ".edu", ".ac.", "europa.eu", "oecd.org", "who.int", "ilo.org",
    "un.org", "unesco.org", "worldbank.org", "imf.org", "nih.gov", "cdc.gov",
    "fda.gov", "europa.", "oecd.", "gov.bd", "ugc.gov.bd",
)
_TIER3_HINTS = (
    "blogspot.", "medium.com", "facebook.com", "linkedin.com", "youtube.com",
    "youtu.be", "tiktok.com", "instagram.com", "reddit.com", "quora.com",
    "einpresswire.com", "prlog.org", "issuewire.com", "24-7pressrelease",
)


def _domain(url: str) -> str:
    try:
        return urlparse(url or "").netloc.lower().lstrip("www.")
    except Exception:
        return ""


def authority_tier(url: str) -> int:
    d = _domain(url)
    if any(d == h.lstrip(".") or d.endswith(h) for h in _TIER1_HINTS):
        return 1
    if any(h in d for h in _TIER3_HINTS):
        return 3
    return 2


def _norm_url(u: str) -> str:
    u = (u or "").strip().lower().rstrip("/")
    u = re.sub(r"[?&](utm_[^=&]*|fbclid|gclid|mc_[^=&]*)[^&]*", "", u)
    return u


def dedup_sources(sources):
    """Exact-URL + near-dup (same domain + near-identical title) dedup."""
    seen_urls = set()
    seen_titles = set()
    out = []
    for s in sources:
        u = _norm_url(s.get("url", ""))
        if not u or u in seen_urls:
            continue
        title_key = (_domain(s.get("url", "")) + "|" +
                     re.sub(r"\s+", " ", (s.get("title") or "")[:60]).casefold())
        if title_key in seen_titles and len(title_key) > 12:
            continue
        seen_urls.add(u)
        seen_titles.add(title_key)
        out.append(s)
    return out


def _relevance_filter(sources, query_topic):
    """Filter out clearly irrelevant sources before ranking and synthesis.
    
    Removes sources that are clearly unrelated to the research topic to prevent
    search noise from reaching the synthesizer (e.g., US university pages when
    researching Bangladesh education).
    """
    if not sources or not query_topic:
        return sources
    
    query_lower = query_topic.lower()
    
    filtered = []
    for s in sources:
        url = s.get("url", "").lower()
        title = s.get("title", "").lower()
        snippet = s.get("snippet", "").lower()
        
        # Skip clearly irrelevant patterns
        should_skip = False
        
        # US university admission pages when not researching US education
        if (".edu" in url and "admission" in url) and not any(
            us_indicator in query_lower for us_indicator in ["united states", "us ", "usa", "american"]
        ):
            should_skip = True
        
        # Consumer finance pages when not researching finance topics
        if ("consumer" in url or "cfpb" in url) and not any(
            finance_indicator in query_lower for finance_indicator in ["finance", "financial", "banking", "credit", "loan"]
        ):
            should_skip = True
        
        # Press release farms (always skip)
        if any(pr_site in url for pr_site in ["einpresswire", "prlog", "issuewire", "24-7pressrelease", "newswire"]):
            should_skip = True
        
        # Keep source if it doesn't match skip patterns
        if not should_skip:
            filtered.append(s)
    
    return filtered


def rank_sources(sources):
    """Rank-then-cap: authority tier first, then search score, then recency."""
    def _key(s):
        tier = authority_tier(s.get("url", ""))
        try:
            score = float(s.get("score") or 0)
        except Exception:
            score = 0
        date = (s.get("published_date") or "")
        return (tier, -score, not bool(date), date)
    return sorted(sources, key=_key)


def _parse_json_obj(raw: str):
    if "```" in raw:
        # Handle markdown code blocks - extract the content between ```
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                raw = part
                break
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(raw[start:end])
    raise ValueError("no JSON object found")


async def _gap_analysis(provider_cfg, question, sources, attempt):
    if not provider_cfg:
        return {"need_more": False, "coverage": 60, "gaps": [], "next_queries": [], "reason": "no llm"}
    src_text = "\n".join(
        [f"[{i}] {s.get('title','')[:80]} | {s.get('snippet','')[:180]}"
         for i, s in enumerate(sources[:8], 1)])
    prompt = (f"Sub-question: {question}\n\nSources collected ({len(sources)}):\n"
              f"{src_text[:2000]}\n\nAttempt {attempt+1}. Evaluate gaps and decide if more search needed.")
    try:
        raw = await asyncio.wait_for(chat_once(provider_cfg, [
            {"role": "system", "content": GAP_ANALYSIS_SYSTEM},
            {"role": "user", "content": prompt}
        ], temperature=0.3, max_tokens=400), timeout=180)
        return _parse_json_obj(raw)
    except asyncio.TimeoutError:
        print("[gap] timeout, treating as sufficient")
        return {"need_more": False, "coverage": 70, "gaps": [], "next_queries": [], "reason": "gap check timed out"}
    except Exception as e:
        print("[gap] parse failed", e)
    return {"need_more": False, "coverage": 70, "gaps": [], "next_queries": [], "reason": "parse fallback"}


async def _extract_contact_info(provider_cfg, sources):
    """Extract contact information from sources for user guidance."""
    if not provider_cfg or not sources:
        return []
    
    chunks = []
    for i, s in enumerate(sources[:12], 1):
        content = ((s.get("content") or s.get("snippet") or "")[:1500]).replace("\n", " ")
        chunks.append(f"[{i}] {s.get('title','')[:100]} | {s.get('url','')}\n{content}")
    
    prompt = """You are a contact information extractor. From the source excerpts, extract ONLY specific contact information.
Look for: names, titles, phone numbers, email addresses, physical addresses, office locations, department names.

Return ONLY JSON:
{
  "contacts": [
    {"name": "...", "title": "...", "phone": "...", "email": "...", "address": "...", "department": "...", "source_idx": 1}
  ]
}
Rules: Only extract if ALL information is clearly present. Don't guess or infer. Max 10 contacts."""
    
    try:
        raw = await asyncio.wait_for(chat_once(provider_cfg, [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Source excerpts:\n" + "\n---\n".join(chunks)[:8000]}
        ], temperature=0.2, max_tokens=600), timeout=120)
        data = _parse_json_obj(raw)
        return data.get("contacts", [])[:10]
    except Exception as e:
        print(f"[contact extraction] failed", e)
        return []


async def _evidence_pass(provider_cfg, qid, question, sources):
    """Extract grounded claims for one sub-question → feeds synthesis + state."""
    if not provider_cfg or not sources:
        return {"claims": [], "open_questions": []}
    chunks = []
    for i, s in enumerate(sources[:8], 1):
        excerpt = ((s.get("content") or s.get("snippet") or "")[:1200]).replace("\n", " ")
        chunks.append(f"[{i}] {s.get('title','')[:100]} | {s.get('url','')}\n{excerpt}")
    prompt = (f"Sub-question [{qid}]: {question}\n\nSource excerpts:\n"
              + "\n---\n".join(chunks)[:9000])
    try:
        raw = await asyncio.wait_for(chat_once(provider_cfg, [
            {"role": "system", "content": EVIDENCE_SYSTEM},
            {"role": "user", "content": prompt}
        ], temperature=0.2, max_tokens=800), timeout=180)
        data = _parse_json_obj(raw)
        claims = data.get("claims", [])[:12]
        return {"claims": claims, "open_questions": data.get("open_questions", [])[:5]}
    except Exception as e:
        print(f"[evidence:{qid}] failed", e)
        return {"claims": [], "open_questions": []}


def _citation_numbers(text: str):
    return sorted({int(n) for n in re.findall(r"\[(\d+)\]", text or "") if int(n) > 0})


CONSULTED_CAP = 40  # max extra consulted-but-uncited sources listed per report


def build_consulted_appendix(ranked, top_n, start_num=None):
    """Appendix listing ranked sources that were reviewed but not directly cited,
    so no fetched source link is ever lost from the report. Numbering continues
    past the cited range; entries carry no inline citations by design."""
    extra = [s for s in ranked[top_n:top_n + CONSULTED_CAP]]
    if not extra:
        return ""
    n0 = start_num if start_num else top_n + 1
    lines = [
        "",
        "## Additional Consulted Sources",
        f"The following {len(extra)} sources were fetched, reviewed, and ranked during "
        "research but are not directly cited above. They are listed for transparency — "
        "all factual claims in this report rest on the cited References.",
        "",
    ]
    for j, s in enumerate(extra):
        title = (s.get("title") or s.get("url", "Untitled"))[:140].replace("\n", " ")
        tier = authority_tier(s.get("url", ""))
        why = f"fetched for {s.get('qid', '?')}" if s.get("qid") else "background"
        lines.append(f"[{n0 + j}] {title} — {s.get('url','')} (Tier-{tier}, {why})")
    return "\n".join(lines) + "\n"


def _mechanical_cite_check(draft: str, k: int):
    """Every [N] must satisfy 1<=N<=K. Returns (ok, problems, coverage)."""
    nums = _citation_numbers(draft)
    problems = []
    oor = [n for n in nums if n < 1 or n > k]
    if oor:
        problems.append(f"Out-of-range citations {oor} exceed source count K={k} — remap to 1..{k}.")
    coverage = (len(nums) / k) if k > 0 else 0
    return (not oor, problems, coverage)


_NUMBER_RE = re.compile(
    r"\$\s?[\d,]+(\.\d+)?"          # $108, $120K handled below via K/M suffix
    r"|\b\d[\d,]*(\.\d+)?\s?%"
    r"|\b\d[\d,]*(\.\d+)?\s?(kWh|Wh|GWh|MW|GW|kW)\b"
    r"|\b\d[\d,]*(\.\d+)?\s?[KMB]\b"
    r"|\b(19|20)\d{2}\b",
    re.IGNORECASE,
)
_CJK_RE = re.compile("[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def _table_citation_check(draft: str):
    """Table rows stating exact numbers must carry an inline [N] citation.

    The jury caught ~30 precise salary/table cells with zero citations.
    Returns a list of issue strings (capped)."""
    def _is_sep(s):
        return re.match(r"^\|?[\s:\-|]+\|?$", s) and "-" in s

    problems = []
    lines = (draft or "").split("\n")
    in_table = False
    for idx, ln in enumerate(lines):
        st = ln.strip()
        if st.startswith("|") and _NUMBER_RE.search(st):
            if _is_sep(st):
                in_table = True
                continue  # separator row
            nxt = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
            if _is_sep(nxt):
                in_table = True
                continue  # header row — data rows below carry the citations
            in_table = True
            if not re.search(r"\[\d+\]", st):
                problems.append(f"Table row states exact figures with no citation: {st[:130]}")
                if len(problems) >= 8:
                    break
        elif not st:
            in_table = False
        elif not st.startswith("|"):
            in_table = False
    return problems


def _language_check(draft: str):
    """Flag non-English residue (e.g. CJK characters from source snippets)."""
    m = _CJK_RE.search(draft or "")
    if m:
        i = max(0, m.start() - 60)
        return [f"Non-English text residue in English report near: …{(draft or '')[i:m.start()+20]}… — translate or remove."]
    return []


async def _conflict_resolution(provider_cfg, conflicts, sources):
    """Resolve conflicts between sources before synthesis."""
    if not provider_cfg or not conflicts:
        return []
    
    if not conflicts:
        return []
    
    prompt = f"""You are a conflict resolution specialist for research. The following conflicts were identified between sources:
{chr(10).join(f"- {c}" for c in conflicts[:5])}

Analyze each conflict and provide:
1. Which source is more authoritative (consider: official vs secondary, recency, specificity)
2. Likely explanation for the discrepancy (different years, different jurisdictions, different definitions)
3. How to present this in the final report (present both with explanation, or prefer one with rationale)

Return ONLY JSON:
{{
  "resolutions": [
    {{"conflict": "...", "preferred_source": "...", "explanation": "...", "presentation": "..."}}
  ]
}}"""
    
    try:
        raw = await asyncio.wait_for(chat_once(provider_cfg, [
            {"role": "system", "content": "You are a research conflict resolution specialist."},
            {"role": "user", "content": prompt}
        ], temperature=0.3, max_tokens=800), timeout=120)
        data = _parse_json_obj(raw)
        return data.get("resolutions", [])[:5]
    except Exception as e:
        print(f"[conflict resolution] failed", e)
        return []


async def _llm_verify(provider_cfg, draft: str, numbered_index: str, k: int):
    try:
        raw = await asyncio.wait_for(chat_once(provider_cfg, [
            {"role": "system", "content": VERIFICATION_SYSTEM},
            {"role": "user", "content": (
                f"K={k} sources. Numbered source index (title — url only):\n{numbered_index[:6000]}"
                f"\n\nDRAFT REPORT:\n{draft[:22000]}")}
        ], temperature=0.2, max_tokens=1200), timeout=240)
        return _parse_json_obj(raw)
    except Exception as e:
        print("[verify] failed", e)
        return {"supported": True, "issues": [], "citation_problems": [],
                "unsourced_numbers": [], "structure_problems": [],
                "hallucination_flags": [f"verify pass failed: {type(e).__name__}"]}


async def run_research_job(job_id, query, plan, progress_cb=None):
    cfg = load_config()
    exa_key = cfg.get("exa_api_key") or cfg.get("providers", {}).get(cfg.get("active_provider"), {}).get("exa_key") or ""
    provider_cfg = get_provider_cfg()
    depth = plan.get("_depth") or "standard"
    dcfg = DEPTH_CFG.get(depth, DEPTH_CFG["standard"])
    sub_qs = plan.get("sub_questions", [])
    all_sources = []
    # per-question evidence state (actually populated now — not display-only)
    q_states = []
    research_state = {"objective": plan.get("title"), "subquestions": [],
                      "sources": [], "claims": [], "conflicts": [], "open_questions": []}

    async def emit(t, d):
        if progress_cb:
            await progress_cb(t, d)

    mode_label = {"quick": "Quick", "standard": "Deep",
                  "deep": "Deeper", "deep_max": "Autonomous Deep Max"}.get(depth, "Deep")
    await emit("stage", {"stage": "planning",
                         "msg": f"Planning: {len(sub_qs)} sub-problems • {dcfg['iters']} max iterations each • {plan.get('strategy','')[:120]}"})
    await emit("thinking", {"msg": f"Starting {mode_label} research: {plan.get('title')}",
                            "total_q": len(sub_qs), "depth": depth})
    await asyncio.sleep(0.2)

    for idx, sq in enumerate(sub_qs):
        qid = sq.get("id", f"Q{idx+1}")
        question = sq.get("question")
        base_queries = sq.get("queries", [])[:dcfg["queries"]]
        await emit("stage", {"stage": "searching", "qid": qid,
                             "msg": f"Q{idx+1}/{len(sub_qs)}: {question[:60]}"})
        await emit("thinking", {"msg": f"[{qid}] Investigating: {question}", "queries": base_queries})

        q_sources, q_gaps, q_conflicts, q_open = [], [], [], []
        iteration = 0
        pending_queries = list(base_queries)

        while iteration < dcfg["iters"]:
            iter_label = f"iter {iteration+1}/{dcfg['iters']}" if dcfg["iters"] > 1 else ""
            for search_q in list(pending_queries):
                await emit("searching", {"qid": qid, "query": search_q,
                                         "progress": f"{idx+1}/{len(sub_qs)} {iter_label}",
                                         "iteration": iteration})
                try:
                    fetched = await asyncio.wait_for(
                        search_and_fetch(search_q, num=6, exa_key=exa_key or None, fetch_top_n=3),
                        timeout=150)
                except asyncio.TimeoutError:
                    await emit("thinking", {"msg": f"[{qid}] search timed out after 150s, continuing with {len(q_sources)} sources"})
                    fetched = []
                except Exception as e:
                    await emit("thinking", {"msg": f"[{qid}] search failed ({type(e).__name__}), continuing"})
                    fetched = []
                for f in fetched:
                    f["qid"] = qid
                    f["question"] = question
                    f["iteration"] = iteration
                    f["authority_tier"] = authority_tier(f.get("url", ""))
                q_sources.extend(fetched)
                all_sources.extend(fetched)
                await emit("reading", {"qid": qid, "query": search_q, "count": len(fetched),
                                       "sources": fetched, "iteration": iteration})
                await emit("fetched", {"qid": qid, "query": search_q, "count": len(fetched),
                                       "sources": fetched})
                await asyncio.sleep(0.25)

            if iteration >= dcfg["iters"] - 1:
                break
            await emit("analyzing", {"qid": qid,
                                     "msg": f"Analyzing coverage for {qid} — {len(q_sources)} sources so far..."})
            gap = await _gap_analysis(provider_cfg, question, q_sources, iteration)
            q_gaps.extend(gap.get("gaps", [])[:4])
            q_conflicts.extend(gap.get("conflicts", [])[:3])
            await emit("gap_analysis", {"qid": qid, "coverage": gap.get("coverage"),
                                        "gaps": gap.get("gaps"), "need_more": gap.get("need_more"),
                                        "reason": gap.get("reason"),
                                        "next_queries": gap.get("next_queries")})
            if not gap.get("need_more") or gap.get("coverage", 0) >= STOP_COVERAGE:
                await emit("thinking", {"msg": f"[{qid}] Coverage {gap.get('coverage')}% — sufficient. {gap.get('reason','')}"})
                break
            next_q = gap.get("next_queries", [])[:2]
            if not next_q:
                break
            await emit("thinking", {"msg": f"[{qid}] Gap ({gap.get('coverage')}%) — {gap.get('reason')} → searching: {', '.join(next_q)}"})
            pending_queries = next_q
            iteration += 1
            if len(q_sources) >= dcfg["per_q"]:
                await emit("thinking", {"msg": f"[{qid}] Source budget reached ({len(q_sources)}/{dcfg['per_q']})"})
                break
            await asyncio.sleep(0.2)

        # ---- evidence extraction pass (claims feed synthesis, not just display) ----
        q_claims = []
        if dcfg["evidence"] and q_sources:
            await emit("analyzing", {"qid": qid,
                                     "msg": f"Extracting evidence claims for {qid} from {len(q_sources)} sources..."})
            ev = await _evidence_pass(provider_cfg, qid, question, rank_sources(q_sources))
            q_claims = ev.get("claims", [])
            q_open.extend(ev.get("open_questions", []))
            await emit("claims", {"qid": qid, "count": len(q_claims), "claims": q_claims,
                                  "open_questions": q_open})

        q_states.append({"id": qid, "question": question, "rationale": sq.get("rationale", ""),
                         "priority": sq.get("priority", ""), "sources": q_sources,
                         "claims": q_claims, "gaps": q_gaps,
                         "conflicts": q_conflicts, "open": q_open})
        research_state["subquestions"].append(
            {"id": qid, "question": question,
             "status": "complete" if len(q_sources) >= 3 else "partial",
             "sources": len(q_sources), "claims": len(q_claims)})
        research_state["claims"].extend([{**c, "qid": qid} for c in q_claims])
        research_state["conflicts"].extend([{"qid": qid, "text": c} for c in q_conflicts])
        research_state["open_questions"].extend([{"qid": qid, "text": o} for o in q_open])

        if provider_cfg and idx < len(sub_qs) - 1:
            await emit("thinking", {"msg": f"Completed {qid} — {len(q_sources)} sources, {len(q_claims)} claims • Next: {sub_qs[idx+1].get('id')}"})

    n_claims = len(research_state["claims"])
    n_conf = len(research_state["conflicts"])
    await emit("stage", {"stage": "verifying",
                         "msg": f"Verifying {len(all_sources)} sources, {n_claims} claims, {n_conf} conflicts..."})
    await emit("analyzing", {"msg": "Evidence graph → conflict check, freshness, citation scope..."})
    
    # ---- relevance filter, rank-then-cap (authority + score + recency), NOT fetch order ----
    deduped = dedup_sources(all_sources)
    filtered = _relevance_filter(deduped, query)
    ranked = rank_sources(filtered)
    top_sources = ranked[:dcfg["cap"]]
    tier_counts = {1: 0, 2: 0, 3: 0}
    for s in top_sources:
        tier_counts[authority_tier(s.get("url", ""))] += 1
    await emit("thinking", {"msg": f"Ranked {len(deduped)} unique sources → top {len(top_sources)} "
                                   f"(Tier-1: {tier_counts[1]}, Tier-2: {tier_counts[2]}, Tier-3: {tier_counts[3]})"})

    # global index used for citations: number -> source
    for i, s in enumerate(top_sources, 1):
        s["_n"] = i

    # Conflict resolution before synthesis
    conflict_resolutions = []
    if research_state["conflicts"] and provider_cfg:
        await emit("analyzing", {"msg": f"Resolving {len(research_state['conflicts'])} source conflicts..."})
        conflict_texts = [c.get("text", "") for c in research_state["conflicts"][:5]]
        conflict_resolutions = await _conflict_resolution(provider_cfg, conflict_texts, top_sources)
        if conflict_resolutions:
            await emit("conflicts_resolved", {"count": len(conflict_resolutions), "resolutions": conflict_resolutions})
    
    # Extract contact information for user guidance
    contacts = []
    if provider_cfg and top_sources:
        await emit("analyzing", {"msg": "Extracting contact information from sources..."})
        contacts = await _extract_contact_info(provider_cfg, top_sources)
        if contacts:
            await emit("contacts", {"count": len(contacts), "contacts": contacts})
    
    await asyncio.sleep(0.4)

    await emit("stage", {"stage": "synthesizing",
                         "msg": f"Synthesizing {len(all_sources)} sources into professional report..."})
    await emit("synthesizing", {"msg": f"Synthesizing {len(all_sources)} sources into professional report...",
                                "sources_count": len(all_sources)})

    if not provider_cfg:
        md = (f"# {plan.get('title')}\n\n## Executive Summary\nResearch on **{query[:200]}** covering "
              f"{len(sub_qs)} dimensions. This is a demo report (configure LLM in Settings for full AI synthesis).\n\n"
              f"## Methodology\nSearched {len(all_sources)} sources across {len(sub_qs)} sub-questions via agent-reach + Jina Reader.\n\n## Key Findings\n")
        for i, s in enumerate(all_sources[:10], 1):
            md += f"- **{s.get('title','')}** — {s.get('snippet','')[:120]} [{i}]\n"
        md += "\n## Bibliography\n"
        for i, s in enumerate(all_sources, 1):
            md += f"{i}. {s.get('title','Untitled')} — {s.get('url','')}\n"
        await emit("stage", {"stage": "complete", "msg": "Report complete (demo)"})
        await emit("done", {"report": md, "sources": all_sources, "state": research_state})
        return md, all_sources

    try:
        def _src_block(i, s, excerpt_len):
            title = (s.get("title") or s.get("url", ""))[:140]
            snippet = (s.get("snippet") or "")[:600].replace("\n", " ")
            excerpt = (s.get("content") or "")[:excerpt_len].replace("\n", " ")
            date = s.get("published_date") or "date unknown"
            tier = authority_tier(s.get("url", ""))
            return (f"[{i}] {title} | {s.get('url','')} | Tier-{tier} | {date}\n"
                    f"Snippet: {snippet}\nExcerpt: {excerpt}\n---\n")

        sources_text = "".join(_src_block(i, s, dcfg["excerpt"]) for i, s in enumerate(top_sources, 1))
        sources_text = sources_text[:GLOBAL_PROMPT_CAP]

        # per-question evidence groups: which numbered sources + claims + gaps answer each Q
        q_groups = []
        
        # Add contact information to the prompt if available
        contacts_section = ""
        if contacts:
            contacts_text = "\n".join(
                f"- {c.get('name','')} ({c.get('title','')}) - {c.get('phone','')} / {c.get('email','')} / {c.get('address','')} [src {c.get('source_idx','?')}]"
                for c in contacts[:8]
            )
            contacts_section = f"\n\nCONTACT INFORMATION FOUND IN SOURCES:\n{contacts_text}\n"
        
        # Add conflict resolutions to the prompt if available
        conflicts_section = ""
        if conflict_resolutions:
            conflicts_text = "\n".join(
                f"- {r.get('conflict','')}: {r.get('presentation','')}"
                for r in conflict_resolutions[:5]
            )
            conflicts_section = f"\n\nCONFLICT RESOLUTIONS:\n{conflicts_text}\n"
        
        for qs in q_states:
            nums = sorted({s.get("_n") for s in top_sources if s.get("qid") == qs["id"] and s.get("_n")})
            if not nums:  # question lost all sources to the cap — keep its best raw ones visible
                best = rank_sources(qs["sources"])[:3]
                extra = []
                for s in best:
                    if s.get("_n") is None:
                        s["_n"] = len(top_sources) + len(extra) + 1
                        top_sources.append(s)
                        extra.append(s)
                nums = sorted({s["_n"] for s in best})
            claims_txt = "\n".join(
                f"- {c.get('text','')} [src {c.get('source_idx')}, {c.get('confidence','?')}]"
                for c in qs["claims"][:10])
            q_groups.append(
                f"{qs['id']}: {qs['question']}\n"
                f"Rationale: {qs.get('rationale','')}\n"
                f"Answering sources: {nums}\n"
                f"Extracted claims:\n{claims_txt or '(none — use source excerpts)'}\n"
                f"Open gaps: {qs['gaps'] or 'none'}\n"
                f"Conflicts: {qs['conflicts'] or 'none'}\n"
                f"Open questions: {qs['open'] or 'none'}")
        # renumber safeguard: sources appended above shift K
        K = len(top_sources)
        numbered_index = "\n".join(
            f"[{s['_n']}] {s.get('title','')[:100]} — {s.get('url','')}" for s in top_sources)

        query_short = query[:600] + ("..." if len(query) > 600 else "")
        prompt = (
            f"Research Topic: {query_short}\nDepth: {depth}\n\n"
            f"EVIDENCE MAP (per sub-question — use the listed sources + claims for each section):\n"
            + "\n\n".join(q_groups) +
            f"\n\nNUMBERED SOURCE LIST — citations [N] MUST refer to these numbers 1..{K}:\n"
            f"{sources_text}\n\n"
            f"{contacts_section}"
            f"{conflicts_section}"
            f"Generate the full professional report now. Bibliography (References) must list "
            f"ALL {K} sources in numeric order with title — url."
        )
        await emit("stage", {"stage": "writing",
                             "msg": f"Writing report via {provider_cfg.get('model')} "
                                    f"({len(prompt)} chars, {K} ranked sources, {n_claims} claims)..."})
        report = await chat_once(provider_cfg, [
            {"role": "system", "content": SYNTHESIZER_SYSTEM},
            {"role": "user", "content": prompt}], temperature=0.5, max_tokens=8000)
        if not report or len(report.strip()) < 300:
            raise RuntimeError(f"LLM returned too short ({len(report)} chars)")

        # ---- verification gate: mechanical first, LLM second, one revise pass ----
        await emit("stage", {"stage": "verifying", "msg": "Running citation-integrity + verification gate..."})
        mech_ok, mech_problems, coverage = _mechanical_cite_check(report, K)
        table_problems = _table_citation_check(report)
        lang_problems = _language_check(report)
        await emit("analyzing", {"msg": f"Citation check: {len(_citation_numbers(report))}/{K} sources cited"
                                        f" ({coverage:.0%} coverage)"
                                        f"{'' if mech_ok else ' — RANGE ERRORS: ' + '; '.join(mech_problems)}"
                                        f"{'' if not table_problems else f' — {len(table_problems)} uncited table rows'}"
                                        f"{'' if not lang_problems else ' — non-English residue found'}"})
        verdict = await _llm_verify(provider_cfg, report, numbered_index, K)
        issues = list(mech_problems) + list(table_problems) + list(lang_problems) + list(verdict.get("issues", []))
        pre_rev_nums = set(_citation_numbers(report))
        if not verdict.get("supported", True) or mech_problems or table_problems or lang_problems:
            await emit("stage", {"stage": "writing",
                                 "msg": f"Verification found {len(issues)} issue(s) — one revise pass..."})
            revise_prompt = (
                f"Revise the DRAFT report below to fix ALL listed issues. Keep the canonical section "
                f"structure. Citations must stay within 1..{K} and match the numbered source list. "
                f"Do not invent sources or numbers. IMPORTANT: preserve every existing [N] citation "
                f"marker — do not drop citations while revising; add missing ones instead.\n\nISSUES:\n" +
                "\n".join(f"- {x}" for x in issues[:14]) +
                f"\n\nNUMBERED SOURCES:\n{numbered_index[:6000]}"
                f"\n\nDRAFT:\n{report[:24000]}")
            revised = await chat_once(provider_cfg, [
                {"role": "system", "content": SYNTHESIZER_SYSTEM + "\nYou are revising, not drafting: fix only what the issues list."},
                {"role": "user", "content": revise_prompt}], temperature=0.3, max_tokens=8000)
            if revised and len(revised.strip()) > 300:
                report = revised
                mech_ok2, mech_problems2, coverage2 = _mechanical_cite_check(report, K)
                dropped = sorted(pre_rev_nums - set(_citation_numbers(report)))
                drop_note = f" — WARNING revise dropped citations {dropped}" if dropped else ""
                await emit("analyzing", {"msg": f"Post-revise check: {len(_citation_numbers(report))}/{K} cited"
                                                f" ({coverage2:.0%}){drop_note}"
                                                f"{'' if mech_ok2 else ' — remaining: ' + '; '.join(mech_problems2)}"})
        appendix = build_consulted_appendix(ranked, len(top_sources))
        if appendix:
            report = report.rstrip() + "\n" + appendix
            await emit("analyzing", {"msg": f"Appendix: {len(ranked) - len(top_sources)} additional consulted sources listed "
                                            f"[{len(top_sources)+1}..{len(top_sources) + min(len(ranked)-len(top_sources), CONSULTED_CAP)}]"})
        await emit("stage", {"stage": "complete",
                             "msg": f"Complete — {len(report)} chars, {len(_citation_numbers(report))} citations"})

    except Exception as e:
        import traceback
        traceback.print_exc()
        await emit("thinking", {"msg": f"LLM synthesis failed: {type(e).__name__} — generating structured local report"})
        is_auth = "unauthorized" in str(e).lower() or "api key" in str(e).lower()
        err_short = "Authentication failed — check API key in Settings" if is_auth else "Model temporarily unavailable"
        title = plan.get("title") or query[:80]
        objective = (plan.get("objective") or "")[:300]

        def _clean(t):
            return t.replace("[", "").replace("]", "").replace("\n", " ")
        
        # Ensure top_sources is available for the exception handler
        if 'top_sources' not in locals() or not top_sources:
            top_sources = ranked[:dcfg["cap"]]
            for i, s in enumerate(top_sources, 1):
                s["_n"] = i
        
        bullets = "\n".join(
            [f"- **[{s.get('_n', i)}] {_clean(s.get('title','Untitled')[:90])}** — "
             f"{_clean((s.get('snippet','')[:200] or s.get('content','')[:200]))} "
             for i, s in enumerate(top_sources[:10], 1)])
        top_list = "\n".join(
            [f"{s.get('_n', i)}. [{_clean(s.get('title','Untitled')[:70])}]({s.get('url')}) — {s.get('qid','')}"
             for i, s in enumerate(top_sources[:18], 1)])
        report = f"""# {title}

> **Local synthesis** — LLM synthesis is temporarily unavailable ({err_short}). Browsed **{len(all_sources)}** sources (**{len(top_sources)}** ranked) via agent-reach. Structured summary below. Click **Regenerate** to retry with LLM when the model is available.

## Executive Summary
{objective or f"Evidence-based overview of **{title}** based on {len(top_sources)} authoritative sources."}

## Key Signals from Sources
{bullets}

## Methodology
- Gemini-style plan: {len(sub_qs)} sub-questions, {len(all_sources)} fetches via Exa + Jina Reader, Tier-1/2/3 authority ranking.
- Sources deduped + ranked, capped at {len(top_sources)} for synthesis.

## Top Sources
{top_list}

## What to Do Next
- Check **Settings → LLM Provider** and click **Test**.
- Then **Regenerate** for full professional report with inline citations [1][2] and verification.

<details><summary>Technical details (for debugging)</summary>

```
{type(e).__name__}: {str(e)[:1200]}
```

</details>
"""
        appendix = build_consulted_appendix(ranked, len(top_sources))
        if appendix:
            report = report.rstrip() + "\n" + appendix
    await emit("done", {"report": report, "sources": all_sources, "state": research_state})
    return report, all_sources
