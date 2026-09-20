const BASE = "";
export async function api(path, opts={}) {
  let r;
  try {
    r = await fetch(BASE+path, {headers:{"Content-Type":"application/json"}, ...opts});
  } catch (e) {
    throw new Error(`Backend not reachable at ${path} — is the FastAPI server running on :8000? (${e.message})`);
  }
  if(!r.ok) {
    let txt = "";
    try { txt = await r.text(); } catch {}
    // Try to parse FastAPI detail
    try { const j = JSON.parse(txt); txt = j.detail || j.message || txt; } catch {}
    throw new Error(txt || `HTTP ${r.status} at ${path}`);
  }
  const ct = r.headers.get("content-type")||"";
  if(ct.includes("application/json")) return r.json();
  return r.text();
}
