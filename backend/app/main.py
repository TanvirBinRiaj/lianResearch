from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response
import json, uuid, asyncio
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from .models.db import get_db, ResearchJob, SessionLocal
from .config import load_config, save_config, get_provider_cfg
from .services.planner import generate_plan
from .services.researcher import run_research_job
from .services.llm.provider import list_models, chat_once
from .services.reach import jina_fetch

app = FastAPI(title="lianResearch API", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# in-memory progress store for SSE (per process lifetime only)
jobs_progress = {}  # job_id -> list of events
running_tasks = {}  # job_id -> asyncio.Task for the live research worker
job_sources = {}    # job_id -> accumulated partial sources (crash-safe via DB persist)


def _trim_event(ev):
    """Trim an event for DB storage: drop bulky page content, keep metadata."""
    try:
        data = dict(ev.get("data") or {})
        if isinstance(data.get("sources"), list):
            data["sources"] = [
                {k: (str(v)[:400] if k in ("snippet", "content") else v)
                 for k, v in (s or {}).items() if k != "content"}
                for s in data["sources"][:20]
            ]
        if isinstance(data.get("report"), str) and len(data["report"]) > 500:
            data["report"] = data["report"][:500] + "…(truncated)"
        return {"type": ev.get("type"), "data": data, "ts": ev.get("ts")}
    except Exception:
        return {"type": ev.get("type"), "data": {}, "ts": ev.get("ts")}


def _persist(job_id, sources=None, progress=None, status=None, report=None):
    """Best-effort durable write with a fresh session (safe to call from workers)."""
    s = SessionLocal()
    try:
        j = s.query(ResearchJob).filter(ResearchJob.id == job_id).first()
        if not j:
            return
        if sources is not None:
            j.sources_json = json.dumps(sources)
        if progress is not None:
            j.progress_json = json.dumps([_trim_event(e) for e in progress[-80:]])
        if status is not None:
            j.status = status
        if report is not None:
            j.report_md = report
        s.commit()
    except Exception as e:
        print("persist failed:", e)
        s.rollback()
    finally:
        s.close()

@app.get("/api/health")
def health():
    cfg = load_config()
    prov = get_provider_cfg()
    return {"ok": True, "active_provider": cfg.get("active_provider"), "providers": list(cfg.get("providers",{}).keys()), "has_llm": prov is not None, "exa_configured": bool(cfg.get("exa_api_key"))}

@app.get("/api/config")
def get_config():
    cfg = load_config()
    # mask keys
    masked = json.loads(json.dumps(cfg))
    for k,v in masked.get("providers",{}).items():
        if "api_key" in v and v["api_key"]:
            v["api_key"] = v["api_key"][:4]+"****"+v["api_key"][-2:] if len(v["api_key"])>6 else "****"
    if masked.get("exa_api_key"):
        masked["exa_api_key"] = masked["exa_api_key"][:4]+"****"
    return masked

@app.put("/api/config")
async def put_config(req: Request):
    body = await req.json()
    # body contains providers, active_provider, exa_api_key
    current = load_config()
    # merge - keep real keys if masked sent
    if "providers" in body:
        for name, pcfg in body["providers"].items():
            if pcfg.get("api_key","").endswith("****") or "****" in pcfg.get("api_key",""):
                # keep old
                if name in current.get("providers",{}):
                    pcfg["api_key"] = current["providers"][name].get("api_key","")
        current["providers"] = body["providers"]
    if "active_provider" in body:
        current["active_provider"] = body["active_provider"]
    if "exa_api_key" in body:
        ek = body["exa_api_key"]
        if "****" in ek:
            pass
        else:
            current["exa_api_key"] = ek
    if "defaults" in body:
        current["defaults"] = body["defaults"]
    save_config(current)
    return {"ok": True}

@app.post("/api/config/test")
async def test_provider(req: Request):
    body = await req.json()
    cfg = body.get("provider") or get_provider_cfg()
    if not cfg:
        raise HTTPException(400, "No provider")
    try:
        # try list models then chat
        try:
            models = await list_models(cfg)
        except Exception as e:
            models = {"error": str(e)}
        pong = await chat_once(cfg, [{"role":"user","content":"Reply with exactly: pong"}], max_tokens=10)
        return {"ok": True, "pong": pong.strip(), "models": models}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/research/plan")
async def create_plan(req: Request, db: Session = Depends(get_db)):
    body = await req.json()
    query = body.get("query","").strip()
    depth = body.get("depth","standard")
    if not query:
        raise HTTPException(400, "query required")
    # pass depth and provider config into generate_plan and store in plan for researcher
    provider_cfg = get_provider_cfg()
    plan = await generate_plan(query, depth, provider_cfg)
    plan["_depth"] = depth
    job_id = uuid.uuid4().hex[:10]
    job = ResearchJob(id=job_id, query=query, depth=depth, status="planned", plan_json=json.dumps(plan), sources_json="[]", report_md="")
    db.add(job); db.commit()
    return {"job_id": job_id, "plan": plan}

@app.post("/api/research/{job_id}/start")
async def start_research(job_id: str, db: Session = Depends(get_db)):
    job = db.query(ResearchJob).filter(ResearchJob.id==job_id).first()
    if not job: raise HTTPException(404, "job not found")
    # don't double-start a live worker
    task = running_tasks.get(job_id)
    if task and not task.done():
        return {"ok": True, "job_id": job_id, "resumed": True}
    plan = json.loads(job.plan_json or "{}")
    jobs_progress[job_id] = []
    job_sources[job_id] = []
    started_at = datetime.now(timezone.utc).isoformat()

    async def cb(t, d):
        ev = {"type": t, "data": d, "ts": datetime.now(timezone.utc).isoformat()}
        jobs_progress[job_id].append(ev)
        # durable checkpoint so a restart/crash never loses everything
        if t == "fetched":
            for s in (d.get("sources") or []):
                job_sources[job_id].append(s)
            _persist(job_id, sources=job_sources[job_id], progress=jobs_progress[job_id])
        elif t in ("done", "error", "gap_analysis", "stage"):
            _persist(job_id, progress=jobs_progress[job_id])

    job.status = "researching"; db.commit()
    query_text = job.query

    async def bg():
        try:
            report, sources = await run_research_job(job_id, query_text, plan, progress_cb=cb)
            jobs_progress[job_id].append({"type": "done", "data": {"report": report, "sources": sources},
                                          "ts": datetime.now(timezone.utc).isoformat()})
            _persist(job_id, sources=sources, report=report, status="done",
                     progress=jobs_progress[job_id])
        except asyncio.CancelledError:
            jobs_progress[job_id].append({"type": "error", "data": {"msg": "Worker cancelled (backend shutting down). Press Restart to resume."},
                                          "ts": datetime.now(timezone.utc).isoformat()})
            _persist(job_id, sources=job_sources.get(job_id, []), status="interrupted",
                     progress=jobs_progress[job_id])
            raise
        except Exception as e:
            import traceback; traceback.print_exc()
            jobs_progress[job_id].append({"type": "error", "data": {"msg": str(e)[:500]},
                                          "ts": datetime.now(timezone.utc).isoformat()})
            _persist(job_id, sources=job_sources.get(job_id, []), status="error",
                     progress=jobs_progress[job_id])
        finally:
            running_tasks.pop(job_id, None)

    running_tasks[job_id] = asyncio.create_task(bg())
    return {"ok": True, "job_id": job_id, "started_at": started_at}

@app.get("/api/research/{job_id}/stream")
async def stream(job_id: str):
    async def gen():
        last = 0
        timeout = 0
        while True:
            lst = jobs_progress.get(job_id, [])
            alive = (job_id in jobs_progress) or (job_id in running_tasks and not running_tasks[job_id].done())
            if not alive:
                # worker gone (backend restarted / crashed): fail fast, don't hang.
                # DB reconcile marks it interrupted; tell the UI right away.
                _persist(job_id, status="interrupted")
                yield f"data: {json.dumps({'type': 'error', 'data': {'msg': 'Research worker lost (backend restarted or crashed). Your plan is safe — press Restart to run it again.', 'code': 'worker_lost'}})}\n\n"
                return
            while last < len(lst):
                ev = lst[last]
                yield f"data: {json.dumps(ev)}\n\n"
                last += 1
                if ev["type"] in ("done", "error"):
                    return
            await asyncio.sleep(0.5)
            timeout += 0.5
            if timeout > 1800:  # 30min hard cap for deep_max
                yield f"data: {json.dumps({'type': 'error', 'data': {'msg': 'timeout after 30min'}})}\n\n"
                return
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.get("/api/research/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(ResearchJob).filter(ResearchJob.id==job_id).first()
    if not job: raise HTTPException(404, "not found")
    try:
        progress = json.loads(job.progress_json or "[]")
    except Exception:
        progress = []
    task = running_tasks.get(job_id)
    return {"job_id": job.id, "query": job.query, "depth": job.depth, "status": job.status,
            "live": bool(task and not task.done()),
            "plan": json.loads(job.plan_json or "{}"), "sources": json.loads(job.sources_json or "[]"),
            "report": job.report_md, "progress": progress}

@app.get("/api/history")
def history(db: Session = Depends(get_db)):
    jobs = db.query(ResearchJob).order_by(ResearchJob.created_at.desc()).limit(50).all()
    return [{"job_id": j.id, "query": j.query, "depth": j.depth, "status": j.status, "created_at": j.created_at.isoformat() if j.created_at else ""} for j in jobs]

@app.delete("/api/history/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(ResearchJob).filter(ResearchJob.id==job_id).first()
    if not job: raise HTTPException(404, "not found")
    db.delete(job); db.commit()
    jobs_progress.pop(job_id, None)
    return {"ok": True}

@app.post("/api/fetch")
async def fetch_url(req: Request):
    body = await req.json()
    url = body.get("url")
    if not url: raise HTTPException(400,"url required")
    data = await jina_fetch(url)
    return data


@app.get("/api/research/{job_id}/export")
def export_report(job_id: str, format: str = "md", db: Session = Depends(get_db)):
    from .services.export import build_docx, build_pdf, safe_filename
    fmt = (format or "md").lower()
    if fmt not in ("md", "markdown", "pdf", "docx", "doc"):
        raise HTTPException(400, "format must be md, pdf or docx")
    job = db.query(ResearchJob).filter(ResearchJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "not found")
    plan = {}
    try:
        plan = json.loads(job.plan_json or "{}")
    except Exception:
        plan = {}
    title = plan.get("title") or (job.query[:80] if job.query else "Research Report")
    fname = safe_filename(title)
    report = job.report_md or ""

    if fmt in ("md", "markdown"):
        from .services.export import clean_query_for_header
        qline = clean_query_for_header(job.query or "")
        # Remove prompt leakage - only include clean topic line, not raw prompt
        head = f"# {title}\n\n"
        if qline:
            head += f"> Research Topic: {qline}\n"
        head += f"> Exported: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')} • lianResearch\n\n"
        body = head + report
        return Response(
            content=body,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}.md"'},
        )
    if fmt == "pdf":
        buf = build_pdf(title, report, job.query or "")
        return Response(
            content=buf.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}.pdf"'},
        )
    buf = build_docx(title, report, job.query or "")
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}.docx"'},
    )
