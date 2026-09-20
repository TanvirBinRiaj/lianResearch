import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { Sparkles, Loader2, Globe, Layers } from 'lucide-react'

export default function NewResearch(){
  const [query,setQuery]=useState('')
  const [depth,setDepth]=useState('standard')
  const [loading,setLoading]=useState(false)
  const nav=useNavigate()
  const [error,setError]=useState('')

  async function start(){
    if(!query.trim()) return
    setLoading(true); setError('')
    try{
      const r = await api('/api/research/plan',{method:'POST', body: JSON.stringify({query, depth})})
      nav(`/research/${r.job_id}`, {state: {plan: r.plan, query}})
    }catch(e){ setError(String(e.message).slice(0,400)) }
    setLoading(false)
  }

  return (
    <div className="max-w-[900px] mx-auto px-8 py-12">
      <div className="mb-10">
        <div className="inline-flex items-center gap-2 text-xs tracking-widest text-indigo-400 border border-indigo-500/30 px-3 py-1 rounded-full bg-indigo-500/10">GEMINI-STYLE DEEP RESEARCH</div>
        <h1 className="text-[40px] font-bold tracking-tight mt-4 leading-none">What do you want to <span className="bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">research deeply?</span></h1>
        <p className="text-zinc-400 mt-3">AI will create a research plan, browse dozens of sites via <span className="text-zinc-200">agent-reach</span>, think and synthesize a professional cited report. <span className="text-indigo-400">Deep Max</span> runs autonomous iterative loop — searches until gaps resolved, like Gemini Deep Research Max.</p>
      </div>

      <div className="rounded-[20px] border border-zinc-800 bg-zinc-900/50 p-2 shadow-2xl">
        <textarea value={query} onChange={e=>setQuery(e.target.value)} placeholder="e.g. Impact of quantum computing on cryptography in 2026, with market and technical analysis..." className="w-full min-h-[140px] bg-transparent p-4 outline-none placeholder:text-zinc-500 text-[15px] resize-none"/>
        <div className="flex items-center justify-between px-3 py-3 border-t border-zinc-800 gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            {[
              ['quick','Quick','5-8 sources'],
              ['standard','Standard','15-20'],
              ['deep','Deep','30+'],
              ['deep_max','Deep Max','Autonomous until clear'],
            ].map(([id,label,sub])=>(
              <button key={id} onClick={()=>setDepth(id)} className={`px-3.5 py-1.5 rounded-full text-xs font-medium border flex flex-col items-start leading-none ${depth===id?'bg-white text-black border-white':'bg-zinc-800 text-zinc-300 border-zinc-700 hover:bg-zinc-700'}`}>
                <span className="font-semibold">{label}</span><span className="text-[10px] opacity-70">{sub}</span>
              </button>
            ))}
          </div>
          <button onClick={start} disabled={loading} className="inline-flex items-center gap-2 bg-white text-black px-6 py-2.5 rounded-full font-semibold hover:bg-zinc-100 disabled:opacity-50">
            {loading?<Loader2 className="w-4 h-4 animate-spin"/>:<Sparkles className="w-4 h-4"/>} Generate Research Plan
          </button>
        </div>
      </div>
      {error && <div className="mt-4 text-sm text-red-400 bg-red-950/30 border border-red-900 p-3 rounded-xl">{error}</div>}

      <div className="grid grid-cols-3 gap-4 mt-8">
        {[
          {icon: Globe, title:"Browses the real web", desc:"Exa + Jina Reader + agent-reach across GitHub, YouTube, news"},
          {icon: Layers, title:"Thinks & plans itself", desc:"Auto-decomposes into sub-questions like Gemini Deep Research"},
          {icon: Sparkles, title:"Professional report", desc:"Executive summary, findings, debates, bibliography with citations"},
        ].map(c=>(
          <div key={c.title} className="rounded-2xl border border-zinc-800 bg-zinc-900/30 p-5">
            <c.icon className="w-5 h-5 text-indigo-400 mb-2"/>
            <div className="font-medium text-sm">{c.title}</div>
            <div className="text-xs text-zinc-500 mt-1">{c.desc}</div>
          </div>
        ))}
      </div>

      <div className="mt-6 flex gap-2 flex-wrap">
        {["AI agents market 2026","Quantum computing breakthroughs","Best open source LLM 2026","Climate tech funding trends"].map(s=>(
          <button key={s} onClick={()=>setQuery(s)} className="text-xs px-3 py-1.5 rounded-full bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-white hover:border-zinc-700">{s}</button>
        ))}
      </div>
    </div>
  )
}
