import asyncio, json, subprocess, urllib.parse
import httpx

# agent-reach integration — zero-config paths first, then exa if key available

async def jina_fetch(url: str, timeout=20):
    jina_url = f"https://r.jina.ai/{url}"
    # also try localhost r.jina.ai http
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.get(jina_url, headers={"User-Agent":"lianResearch/1.0"})
            if r.status_code==200 and len(r.text)>300:
                return {"url": url, "content": r.text[:15000], "title": url, "status":"ok"}
    except Exception as e:
        return {"url": url, "content": f"fetch failed: {e}", "status":"error"}
    return {"url": url, "content":"", "status":"error"}

async def exa_search(query: str, num=5, api_key=None):
    # Use Exa API directly if key provided; fallback to curl jina search? We use Exa HTTP.
    if not api_key:
        # fallback: try agent-reach via python? just return empty to use jina google hack
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post("https://api.exa.ai/search", headers={"x-api-key": api_key, "Content-Type":"application/json"},
                json={"query": query, "numResults": num, "type":"auto",
                      "contents": {"text": {"maxCharacters": 3000}}})
            if r.status_code==200:
                j=r.json()
                out=[]
                for item in j.get("results",[]):
                    out.append({"title": item.get("title",""), "url": item.get("url"),
                                "snippet": item.get("text","")[:800],
                                "score": item.get("score"),
                                "published_date": item.get("publishedDate"),
                                "author": item.get("author")})
                return out
    except Exception as e:
        print("exa error", e)
    return []

async def tavily_search_fallback(query, num=5):
    # No key needed path: use DuckDuckGo via jina? Simple jina search via https://r.jina.ai/http://cc.bingj.com/cache.cgi?d=... not reliable.
    # Fallback: use exa without key -> try via jina search of google
    # We implement a minimal Serp via Jina's s.jina.ai search
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            q = urllib.parse.quote(query)
            r = await c.get(f"https://s.jina.ai/{q}", headers={"User-Agent":"lianResearch/1.0"})
            if r.status_code==200:
                # jina search returns markdown list of results
                txt=r.text[:15000]
                # crude parse lines with http
                import re
                urls=re.findall(r'https?://[^\s\)]+', txt)
                uniq=[]
                for u in urls:
                    u=u.rstrip('.,)')
                    if u not in uniq: uniq.append(u)
                    if len(uniq)>=num: break
                return [{"title": u, "url": u, "snippet":""} for u in uniq]
    except Exception as e:
        print("jina s search fail", e)
    return []

async def search_and_fetch(query, num=5, exa_key=None, fetch_top_n=3):
    results=[]
    if exa_key:
        results = await exa_search(query, num, exa_key)
    if not results:
        results = await tavily_search_fallback(query, num)
    # fetch full page content for top N (researcher trims excerpts per depth budget)
    fetched=[]
    for it in results[:fetch_top_n]:
        url=it.get("url")
        if not url: continue
        # Exa already returns up to 3000 chars of page text; only Jina-fetch when thin
        if len(it.get("snippet") or "") >= 1200:
            fetched.append({**it, "content": it.get("snippet") or ""})
            continue
        fetched_content = await jina_fetch(url)
        content = fetched_content.get("content","")[:8000]
        # keep whichever is richer
        if len(content) < len(it.get("snippet") or ""):
            content = it.get("snippet") or ""
        fetched.append({**it, "content": content})
    return fetched

# subprocess helper for agent-reach doctor / youtube etc (optional)
async def run_agent_reach_search(platform_cmd: str):
    try:
        proc = await asyncio.create_subprocess_shell(platform_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=25)
        return out.decode()[:8000]
    except Exception as e:
        return f"error: {e}"
