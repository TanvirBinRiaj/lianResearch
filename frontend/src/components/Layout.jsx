import { NavLink } from 'react-router-dom'
import { Search, History, Settings, Sparkles, Beaker, CircleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export default function Layout({children}){
  const [health,setHealth]=useState(null)
  useEffect(()=>{
    let alive=true
    const fetchHealth=()=> api('/api/health').then(d=>{ if(alive) setHealth(d)}).catch(()=>{ if(alive) setHealth({ok:false})})
    fetchHealth()
    const id=setInterval(fetchHealth, 30000) // 30s, was 10s spamming logs
    // also listen for visibility change to avoid background spam
    const onVis=()=>{ if(document.visibilityState==='visible') fetchHealth() }
    document.addEventListener('visibilitychange', onVis)
    return ()=>{ alive=false; clearInterval(id); document.removeEventListener('visibilitychange', onVis)}
  },[])
  return (
    <div className="min-h-screen flex bg-[#0a0a0f]">
      <aside className="w-[260px] shrink-0 border-r border-zinc-800 bg-zinc-950/50 backdrop-blur flex flex-col sticky top-0 h-screen">
        <div className="p-6 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center"><Beaker className="w-5 h-5 text-white"/></div>
          <div><div className="font-bold leading-none">lianResearch</div><div className="text-xs text-zinc-500">Deep Research Lab</div></div>
        </div>
        <nav className="px-3 space-y-1 flex-1">
          <NavLink to="/" className={({isActive})=>`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm ${isActive?'bg-zinc-900 text-white':'text-zinc-400 hover:bg-zinc-900 hover:text-white'}`}><Sparkles className="w-4 h-4"/> New Research</NavLink>
          <NavLink to="/history" className={({isActive})=>`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm ${isActive?'bg-zinc-900 text-white':'text-zinc-400 hover:bg-zinc-900 hover:text-white'}`}><History className="w-4 h-4"/> History</NavLink>
          <NavLink to="/settings" className={({isActive})=>`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm ${isActive?'bg-zinc-900 text-white':'text-zinc-400 hover:bg-zinc-900 hover:text-white'}`}><Settings className="w-4 h-4"/> Settings</NavLink>
        </nav>
        {health && !health.ok && (
          <div className="mx-3 mb-3 rounded-xl bg-red-950/40 border border-red-900 p-3 text-xs text-red-300 flex gap-2"><CircleAlert className="w-4 h-4 shrink-0"/> Backend offline — start with <code className="bg-black/30 px-1 rounded">./backend/.venv/bin/uvicorn app.main:app --port 8000</code></div>
        )}
        {health?.ok && (
          <div className="mx-3 mb-3 rounded-xl bg-zinc-900 border border-zinc-800 p-2 text-[11px] text-zinc-400">
            <div className="flex items-center gap-1.5"><span className={`w-2 h-2 rounded-full ${health.has_llm?'bg-emerald-500':'bg-amber-500'}`}/> LLM {health.has_llm?'ready':'not configured'}</div>
            <div className="text-[11px] text-zinc-500">{health.providers?.join(', ')||'no provider'} {health.exa_configured?'• Exa ✓':''}</div>
          </div>
        )}
        <div className="p-4 border-t border-zinc-800 text-xs text-zinc-500">
          Uses <span className="text-zinc-300">agent-reach</span> for web • Jina Reader • Exa
          <div className="mt-2 text-[11px]">Modern • Deep • Cited</div>
        </div>
      </aside>
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  )
}
