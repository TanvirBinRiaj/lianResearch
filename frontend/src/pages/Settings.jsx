import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Check, Loader2, Eye, EyeOff } from 'lucide-react'

const PROVIDER_TEMPLATES = [
  {id:"openai", name:"OpenAI", base:"https://api.openai.com/v1", model:"gpt-4o-mini"},
  {id:"openrouter", name:"OpenRouter", base:"https://openrouter.ai/api/v1", model:"openai/gpt-4o-mini"},
  {id:"anthropic", name:"Anthropic (OpenAI-compat via proxy)", base:"https://api.anthropic.com/v1", model:"claude-3-5-sonnet-latest"},
  {id:"gemini", name:"Google Gemini (OpenAI compat)", base:"https://generativelanguage.googleapis.com/v1beta/openai", model:"gemini-2.0-flash"},
  {id:"ollama", name:"Ollama Local", base:"http://localhost:11434/v1", model:"llama3.1"},
  {id:"lmstudio", name:"LM Studio", base:"http://localhost:1234/v1", model:"local-model"},
]

export default function Settings(){
  const [cfg,setCfg]=useState(null)
  const [saving,setSaving]=useState(false)
  const [testing,setTesting]=useState(false)
  const [msg,setMsg]=useState('')
  const [showKey,setShowKey]=useState({})

  const [loadError,setLoadError]=useState('')
  useEffect(()=>{ api('/api/config').then(c=>{
    // ensure at least one provider exists
    if(!c.providers || Object.keys(c.providers).length===0){
      c.providers = {openai:{base_url:"https://api.openai.com/v1", api_key:"", model:"gpt-4o-mini"}}
      c.active_provider="openai"
    }
    setCfg(c)
  }).catch(e=>setLoadError(String(e.message))) },[])

  if(loadError) return <div className="p-8"><div className="rounded-xl border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">Backend unreachable: {loadError}<div className="text-xs text-red-400/70 mt-2">Fix: run <code className="bg-black/30 px-1">.venv/bin/uvicorn app.main:app --port 8000</code> in backend. See /tmp/lian_backend.log</div></div></div>
  if(!cfg) return <div className="p-8 text-zinc-400">Loading config...</div>

  function updateProvider(name, field, val){
    setCfg({...cfg, providers:{...cfg.providers, [name]: {...cfg.providers[name], [field]: val}}})
  }
  async function save(){
    setSaving(true); setMsg('')
    try{ await api('/api/config',{method:'PUT', body: JSON.stringify(cfg)}); setMsg('Saved ✓ encrypted at rest') }catch(e){ setMsg(String(e.message)) }
    setSaving(false)
  }
  async function test(name){
    setTesting(name); setMsg('')
    try{
      const prov = cfg.providers[name]
      const r = await api('/api/config/test',{method:'POST', body: JSON.stringify({provider: prov})})
      setMsg(`Test ${name}: pong=${r.pong?.slice(0,60)} models=${JSON.stringify(r.models).slice(0,120)}`)
    }catch(e){ setMsg(`Test failed: ${e.message}`)}
    setTesting(false)
  }

  return (
    <div className="max-w-[860px] mx-auto p-8">
      <h1 className="text-2xl font-bold">Settings</h1>
      <p className="text-sm text-zinc-500 mt-1">Configure AI model API from GUI — no .env needed. Keys are encrypted with Fernet.</p>

      <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
        <h3 className="font-semibold text-sm">Agent-Reach / Internet Access</h3>
        <p className="text-xs text-zinc-500 mt-1">Exa is the primary semantic search backend for agent-reach. Jina Reader is fallback (no key). Configure Exa key to enable 30+ site deep browsing.</p>
        <div className="mt-3 flex gap-2">
          <input value={cfg.exa_api_key||''} onChange={e=>setCfg({...cfg, exa_api_key:e.target.value})} placeholder="exa_•••• (from exa.ai)" className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-2 text-sm outline-none focus:border-indigo-500"/>
        </div>
        <div className="text-xs text-zinc-600 mt-2">Get: https://exa.ai • Leave empty to use Jina search fallback.</div>
      </div>

      <div className="mt-6 flex items-center justify-between">
        <h3 className="font-semibold">LLM Providers</h3>
        <select value={cfg.active_provider||''} onChange={e=>setCfg({...cfg, active_provider:e.target.value})} className="bg-zinc-900 border border-zinc-800 rounded-xl px-3 py-1.5 text-sm">
          {Object.keys(cfg.providers||{}).map(k=> <option key={k} value={k}>{k}</option>)}
        </select>
        <span className="text-xs text-zinc-500">Active provider used for planning & report</span>
      </div>

      <div className="grid gap-4 mt-3">
        {Object.entries(cfg.providers||{}).map(([name, prov])=>(
          <div key={name} className={`rounded-2xl border p-5 ${cfg.active_provider===name?'border-indigo-500/40 bg-indigo-500/5':'border-zinc-800 bg-zinc-900/30'}`}>
            <div className="flex items-center justify-between">
              <div className="font-medium text-sm">{name} {cfg.active_provider===name && <span className="text-xs bg-indigo-500 text-white px-2 py-0.5 rounded-full ml-2">active</span>}</div>
              <div className="flex gap-2">
                <button onClick={()=>test(name)} disabled={testing===name} className="text-xs px-3 py-1.5 rounded-full bg-white text-black disabled:opacity-50 flex items-center gap-1">{testing===name?<Loader2 className="w-3 h-3 animate-spin"/>:null} Test</button>
                <button onClick={()=>{const c={...cfg.providers}; delete c[name]; setCfg({...cfg, providers:c})}} className="text-xs px-3 py-1.5 rounded-full border border-zinc-700 text-zinc-400">Remove</button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <label className="text-xs text-zinc-500">Base URL <input value={prov.base_url||''} onChange={e=>updateProvider(name,'base_url',e.target.value)} className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white"/></label>
              <label className="text-xs text-zinc-500">Model <input value={prov.model||''} onChange={e=>updateProvider(name,'model',e.target.value)} className="mt-1 w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white"/></label>
            </div>
            <label className="text-xs text-zinc-500 mt-3 block">API Key
              <div className="flex gap-2 mt-1">
                <input type={showKey[name]?'text':'password'} value={prov.api_key||''} onChange={e=>updateProvider(name,'api_key',e.target.value)} placeholder="sk-..." className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-white"/>
                <button onClick={()=>setShowKey({...showKey, [name]:!showKey[name]})} className="p-2 bg-zinc-800 rounded-lg">{showKey[name]?<EyeOff className="w-4 h-4"/>:<Eye className="w-4 h-4"/>}</button>
              </div>
            </label>
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-2 flex-wrap">
        <span className="text-xs text-zinc-500">Add template:</span>
        {PROVIDER_TEMPLATES.map(t=>(
          <button key={t.id} onClick={()=>setCfg({...cfg, providers:{...cfg.providers, [t.id]:{base_url:t.base, api_key:"", model:t.model}}})} className="text-xs px-3 py-1.5 rounded-full bg-zinc-800 border border-zinc-700 hover:bg-zinc-700">{t.name}</button>
        ))}
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button onClick={save} disabled={saving} className="px-6 py-2.5 rounded-full bg-white text-black font-semibold flex items-center gap-2 disabled:opacity-50">{saving?<Loader2 className="w-4 h-4 animate-spin"/>:<Check className="w-4 h-4"/>} Save Configuration</button>
        <span className="text-sm text-zinc-400">{msg}</span>
      </div>

      <div className="mt-6 text-xs text-zinc-600 border-t border-zinc-800 pt-4">
        Backend health: <code className="bg-zinc-900 px-2 py-1 rounded">GET /api/health</code> • Keys stored in <code>backend/data/config.enc.json</code> (Fernet)
      </div>
    </div>
  )
}
