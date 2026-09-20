# lianResearch — Professional Deep Research Workbench

Modern **Python (FastAPI) + React + Tailwind** app for **Gemini-style deep research**: AI auto-generates a research plan → browses dozens of sites via **agent-reach** → thinks → produces a professional cited report.

> GUI for configuring LLM API keys, Exa key, model, base_url — no .env needed. Encrypted at rest.

---

## ⚡ Quick Start

```bash
# Clone
git clone https://github.com/TanvirBinRiaj/lianResearch.git
cd lianResearch

# Backend (needs python3.11)
cd backend
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (second terminal)
cd ../frontend
npm install
npm run dev   # → http://localhost:5173 (proxies /api to :8000)
```

Or one-shot: `./start.sh`

---

## 🧠 What It Does

- **Auto Research Plan** — LLM decomposes topic into 5-8 sub-questions with search queries (planner prompt).
- **Deep Browse via agent-reach** — `Exa` semantic search + `Jina Reader` fallback, plus YouTube/V2EX/GitHub via agent-reach channels. Wide coverage (15-45 sources depending on depth).
- **Evidence Extraction** — per-sub-question claims extraction (`EVIDENCE_SYSTEM`).
- **Gap Detection Loop** — iterative re-search until coverage sufficient (all depths now).
- **Rank-Then-Cap Sourcing** — authority tiering (Tier-1 .gov/.edu > Tier-3 blogs), recency boost, near-dedup.
- **Verification Gate** — mechanical citation-range check + LLM verify pass + one auto-revise pass if issues found.
- **Professional Report** — Markdown with Executive Summary, Methodology, Key Findings, Deep Dives, Bibliography with inline `[1][2]` citations.
- **Consulted-Sources Appendix** — all ranked but uncited sources listed at end for transparency.
- **Export** — PDF, Word (.docx), Markdown downloads with real clickable links.

### Depths

| Depth | Iterations/Q | Sources/Q | Total cap | Use case |
|---|---|---|---|---|
| **Quick** | 1 | 6 | 15 | Fast facts |
| **Standard** | 2 | 8 | 28 | Regular research |
| **Deep** | 3 | 10 | 35 | In-depth analysis |
| **Deep Max** | 4 | 12 | 45 | Maximum coverage |

---

## 🏗️ Architecture

```
lianResearch/
├── backend/app/
│   ├── main.py              # FastAPI, CORS, SSE streaming, export endpoints
│   ├── config.py            # pydantic-settings, Fernet-encrypted api_keys.json
│   ├── models/db.py         # SQLAlchemy + SQLite schema + crash recovery
│   ├── services/
│   │   ├── llm/provider.py  # OpenAI-compat adapter (OpenAI/OpenRouter/Gemini/Ollama/LM Studio)
│   │   ├── planner.py       # Gemini-style plan generator
│   │   ├── researcher.py    # Agentic loop: plan → search → evidence → gap-check → synthesize → verify
│   │   ├── reach.py         # agent-reach wrapper: Exa search + Jina Reader
│   │   └── export.py        # PDF (reportlab) + DOCX (python-docx) + MD exports
│   └── prompts/planner.py   # PLANNER/SYNTHESIZER/EVIDENCE/VERIFICATION/GAP_SYSTEM prompts
├── frontend/src/
│   ├── pages/               # NewResearch, ResearchLive, History, Settings
│   ├── components/          # Layout, MarkdownRenderer
│   └── lib/                 # api.js, normalizeMarkdown.js
└── start.sh                 # One-command launcher
```

---

## 🔑 Configuration (GUI)

**Settings → LLM Providers:**
- OpenAI, OpenRouter, Anthropic (via proxy), Google Gemini, Ollama, LM Studio
- Base URL, Model name, API Key (masked, Fernet encrypted at rest)
- **Test** button verifies connectivity + lists models

**Agent-Reach / Internet Access:**
- Exa API key field (get from https://exa.ai)
- If empty, falls back to Jina search (`s.jina.ai`)
- `agent-reach doctor --json` verified: Jina Reader (ok), B站 search API, yt-dlp, V2EX, RSS

---

## 📊 API

```
GET    /api/health
GET    /api/config                     # mask keys
PUT    /api/config                     # save encrypted
POST   /api/config/test                # test provider ping
POST   /api/research/plan              # {query, depth} → plan
POST   /api/research/{id}/start        # fire async worker, return immediately
GET    /api/research/{id}/stream       # SSE: stage/thinking/searching/reading/fetched/analyzing/gap_analysis/synthesizing/writing/complete/done/error
GET    /api/research/{id}              # job state + saved progress
GET    /api/research/{id}/export?format={md|pdf|docx}
GET    /api/history                    # SQLite listing
DELETE /api/history/{job_id}
```

---

## 🔒 Privacy & Security

- API keys encrypted with **Fernet** (symmetric) → stored in `backend/data/config.enc.json`
- Keys never logged, never sent to third parties except the configured LLM provider
- No telemetry, no analytics, no phone-home
- SQLite local database (`backend/data/research.db`) — your research stays local
- `~/.ssh/id_ed25519` / GPG keys NOT touched

---

## 🐛 Known Limitations & Fixes Applied

| Issue | Status |
|---|---|
| Prompt leakage in headers | ✅ Fixed — sanitized at export |
| Citation-number drift | ✅ Fixed — verification gate + mechanical range check |
| Missing table citations | ✅ Fixed — `_table_citation_check()` gate |
| CJK residue in reports | ✅ Fixed — `_language_check()` gate |
| Single-pass synthesis | ✅ Fixed — per-Q evidence extraction + gap loop on all depths |
| Authority unweighted | ✅ Fixed — Tier-1/2/3 ranking before cap |
| Source noise in results | ✅ Fixed — relevance filter in rank pipeline |
| Stuck jobs on restart | ✅ Fixed — crash recovery + interrupt detection |
| Export link quality | ✅ Fixed — real `<link>` tags in PDF, hyperlinks in DOCX |

---

## 🧪 Testing & Benchmarking

Run the agent panel comparison:
```bash
# Compare lianReport vs ChatGPT vs Perplexity on same query
python3 - << 'EOF'
# (see /home/tanvir/Downloads/lian_research_improvement_report.md for full panel results)
EOF
```

Latest benchmark (19 Sep 2026):
- **lian**: 8.6/10 vs Gemini standard (lead by 0.3 over Perplexity, beat ChatGPT by 3.8)
- Remaining gaps: Private Candidate/RPL pathways unsearched, DSHE notification inaccessible

---

## 🤝 Contributing

1. Fork → create feature branch
2. Make changes (Python 3.11+, Node 20+, Tailwind 3)
3. Test: `./start.sh` then visit `http://localhost:5173`
4. Run new research job and verify export quality
5. PR with description of what was fixed/added

---

## 📄 License

MIT — see [LICENSE](LICENSE)

---

*Built with agent-reach, FastAPI, React 19, Tailwind 3, reportlab, python-docx, rehype, remark*
