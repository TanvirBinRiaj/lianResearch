#!/bin/bash
set -e
ROOT=$(cd "$(dirname "$0")" && pwd)
echo "== lianResearch =="
echo "Starting backend on :8000 ..."
cd "$ROOT/backend"
if [ ! -d .venv ]; then python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt; fi
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BE_PID=$!
echo "Backend PID $BE_PID"
echo "Starting frontend on :5173 ..."
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then npm install; fi
npm run dev -- --host 0.0.0.0 --port 5173
kill $BE_PID 2>/dev/null || true
