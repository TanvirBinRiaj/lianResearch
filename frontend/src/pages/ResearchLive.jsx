import { useEffect, useState, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../lib/api'
import MarkdownRenderer from '../components/MarkdownRenderer'
import { Loader2, Check, Globe, Brain, FileText, ExternalLink, Download, FileDown, FileText as FileTextIcon, AlertTriangle, RotateCcw } from 'lucide-react'

export default function ResearchLive(){
  const {id}=useParams()
  const [plan,setPlan]=useState(null)
  const [events,setEvents]=useState([])
  const [report,setReport]=useState('')
  const [sources,setSources]=useState([])
  const [status,setStatus]=useState('planning')
  const [editing,setEditing]=useState(false)
  const [mobileTab, setMobileTab]=useState('report') // report | plan | sources
  const [errMsg,setErrMsg]=useState('')
  const [stalled,setStalled]=useState(false)
  const lastEventAt = useRef(Date.now())

  useEffect(()=>{
    (async()=>{
      const j = await api(`/api/research/${id}`)
      setPlan(j.plan); setReport(j.report||''); setSources(j.sources||[]); setStatus(j.status)
      lastEventAt.current = Date.now()
      if(j.status==='planned'){
        await api(`/api/research/${id}/start`,{method:'POST'})
        setStatus('researching')
      }
    })()
  },[id])

  useEffect(()=>{
    if(status!=='researching' && status!=='planned') return
    lastEventAt.current = Date.now()
    setStalled(false)
    const es = new EventSource(`/api/research/${id}/stream`)
    es.onmessage = e=>{
      const ev = JSON.parse(e.data)
      lastEventAt.current = Date.now()
      setStalled(false)
      setEvents(prev=>[...prev, ev])
      if(ev.type==='fetched') setSources(prev=>[...prev, ...(ev.data.sources||[])])
      if(ev.type==='done'){ setReport(ev.data.report); setStatus('done'); es.close() }
      if(ev.type==='error'){ setErrMsg(ev.data.msg||'Research failed'); setStatus(ev.data.code==='worker_lost'?'interrupted':'error'); es.close() }
    }
    es.onerror=()=> es.close()
    // watchdog: no SSE traffic for 150s means the worker is wedged — say so loudly
    const wd = setInterval(()=>{
      if((status==='researching'||status==='planned') && Date.now()-lastEventAt.current > 150000){
        setStalled(true)
      }
    }, 15000)
    return ()=> { es.close(); clearInterval(wd) }
  },[status, id])

  async function regenerate(){
    setErrMsg(''); setStalled(false)
    setStatus('researching'); setEvents([]); setReport('')
    lastEventAt.current = Date.now()
    try {
      await api(`/api/research/${id}/start`,{method:'POST'})
    } catch(e) {
      setErrMsg(String(e.message).slice(0,300)); setStatus('error')
    }
  }

  const [downloading, setDownloading] = useState(null)
  function downloadFile(format){
    setDownloading(format)
    const url = `/api/research/${id}/export?format=${format}`
    fetch(url).then(async (r)=>{
      if(!r.ok) throw new Error(await r.text())
      const blob = await r.blob()
      const dispo = r.headers.get('Content-Disposition') || ''
      const m = dispo.match(/filename="?([^";]+)"?/)
      const filename = m ? m[1] : `research-${id}.${format === 'docx' ? 'docx' : format}`
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = filename
      document.body.appendChild(a)
      a.click()
      setTimeout(()=>{ URL.revokeObjectURL(a.href); a.remove() }, 500)
      setDownloading(null)
    }).catch((e)=>{
      alert(`Download failed: ${String(e.message).slice(0,300)}`)
      setDownloading(null)
    })
  }

  if(!plan) return <div className="p-10 text-zinc-400 flex gap-2"><Loader2 className="animate-spin"/> Loading plan...</div>

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <div className="sticky top-0 z-20 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur supports-[backdrop-filter]:bg-zinc-950/70 px-4 lg:px-6 py-3 flex items-center justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-[11px] tracking-widest text-zinc-500 font-medium">RESEARCH JOB {id}</div>
          <div className="font-semibold text-sm lg:text-[15px] leading-tight truncate pr-2">{plan.title}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`hidden sm:inline-flex text-xs px-2.5 py-1 rounded-full border font-medium ${status==='done'?'bg-emerald-500/10 text-emerald-400 border-emerald-500/20':(status==='interrupted'||status==='error')?'bg-red-500/10 text-red-400 border-red-500/20':'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>{status}</span>
          <Link to="/" className="text-xs px-3 py-1.5 rounded-full border border-zinc-700 hover:bg-zinc-800 hover:text-white transition">New</Link>
          {status==='done' && <button onClick={regenerate} className="text-xs px-3.5 py-1.5 rounded-full bg-white text-black font-medium hover:bg-zinc-100 transition">Regenerate</button>}
          {(status==='interrupted'||status==='error') && <button onClick={regenerate} className="inline-flex items-center gap-1.5 text-xs px-3.5 py-1.5 rounded-full bg-amber-400 text-black font-semibold hover:bg-amber-300 transition"><RotateCcw className="w-3 h-3"/> Restart</button>}
        </div>
      </div>

      {/* Mobile tabs */}
      <div className="lg:hidden sticky top-[65px] z-10 bg-zinc-950 border-b border-zinc-800 flex">
        {[
          ['report','Report'],
          ['plan','Plan'],
          ['sources',`Sources • ${sources.length}`],
        ].map(([k,label])=>(
          <button key={k} onClick={()=>setMobileTab(k)} className={`flex-1 py-2.5 text-xs font-medium border-b-2 transition ${mobileTab===k?'border-indigo-500 text-white bg-zinc-900':'border-transparent text-zinc-500'}`}>{label}</button>
        ))}
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[340px_1fr] xl:grid-cols-[360px_1fr_340px] min-h-0">
        {/* Plan — left */}
        <div className={`${mobileTab!=='plan'?'hidden lg:flex':''} flex-col border-zinc-800 bg-zinc-950 lg:border-r min-h-0 lg:sticky lg:top-[65px] lg:h-[calc(100vh-65px)] lg:overflow-y-auto`}>
          <div className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[11px] tracking-[0.12em] text-zinc-500 font-semibold">RESEARCH PLAN</h3>
              <button onClick={()=>setEditing(!editing)} className="text-xs text-indigo-400 hover:text-indigo-300">{editing?'Done':'Edit'}</button>
            </div>
            <div className="text-xs leading-relaxed text-zinc-300 break-words bg-zinc-900/50 border border-zinc-800 rounded-xl p-3">{plan.objective}</div>
            <div className="text-[11px] leading-relaxed text-zinc-500 mt-3 break-words">Strategy: {plan.strategy}</div>
            <div className="space-y-3 mt-4">
              {plan.sub_questions?.map((sq)=>(
                <div key={sq.id} className="rounded-xl border border-zinc-800 bg-zinc-900 p-3.5">
                  <div className="text-xs font-semibold text-white leading-snug break-words">{sq.id}: {sq.question}</div>
                  <div className="text-[11px] text-zinc-500 mt-1.5 leading-relaxed break-words">{sq.rationale} <span className="text-zinc-600">• {sq.priority}</span></div>
                  <div className="flex flex-wrap gap-1.5 mt-2.5">
                    {sq.queries?.map(q=> <span key={q} className="text-[11px] px-2.5 py-1 rounded-full bg-zinc-800 border border-zinc-700/50 text-zinc-400 break-all leading-tight">{q}</span>)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Report — center */}
        <div className={`${mobileTab!=='report'?'hidden lg:block':''} bg-[#0a0a0f] min-w-0 min-h-0 lg:overflow-y-auto lg:h-[calc(100vh-65px)]`}>
          {status!=='done' ? (
            <div className="p-4 lg:p-6">
              {(status==='interrupted'||status==='error') && (
                <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 flex gap-3 items-start">
                  <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5"/>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-sm text-amber-200">Research {status==='interrupted'?'interrupted':'failed'} — your plan and {sources.length} sources are safe</div>
                    <div className="text-xs text-amber-200/70 mt-1 break-words">{errMsg || 'The research worker stopped unexpectedly (backend restart or crash). Nothing is lost.'}</div>
                    <button onClick={regenerate} className="mt-3 inline-flex items-center gap-2 text-xs px-4 py-2 rounded-full bg-amber-400 text-black font-semibold hover:bg-amber-300 transition">
                      <RotateCcw className="w-3.5 h-3.5"/> Restart research
                    </button>
                  </div>
                </div>
              )}
              {stalled && status!=='interrupted' && status!=='error' && (
                <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 flex gap-3 items-start">
                  <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5"/>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-sm text-amber-200">No updates for 2+ minutes</div>
                    <div className="text-xs text-amber-200/70 mt-1">The worker may be wedged on a slow search. You can wait, or restart — {sources.length} sources collected so far are kept.</div>
                    <button onClick={regenerate} className="mt-3 inline-flex items-center gap-2 text-xs px-4 py-2 rounded-full bg-amber-400 text-black font-semibold hover:bg-amber-300 transition">
                      <RotateCcw className="w-3.5 h-3.5"/> Restart research
                    </button>
                  </div>
                </div>
              )}
              <h3 className="flex items-center gap-2 font-semibold text-white"><Brain className="w-4 h-4 text-violet-400"/> Live Research <span className="ml-auto text-[11px] font-normal text-zinc-500">{plan._depth==='deep_max'?'Autonomous Max — searches until clear':'Standard'}</span></h3>
              {/* Gemini-style stage bar */}
              <div className="mt-3 flex items-center gap-1.5 text-[10px] tracking-wide">
                {[
                  ['planning','Planning'],
                  ['searching','Searching'],
                  ['reading','Reading'],
                  ['analyzing','Analyzing'],
                  ['verifying','Verifying'],
                  ['writing','Writing'],
                ].map(([id,label])=>{
                  const active = events.some(e=> (e.type==='stage' && e.data.stage===id) || (id==='searching' && e.type==='searching') || (id==='reading' && (e.type==='reading'||e.type==='fetched')) || (id==='analyzing' && (e.type==='analyzing'||e.type==='gap_analysis')) || (id==='writing' && e.type==='synthesizing'))
                  const done = events.some(e=> e.type==='stage' && e.data.stage==='complete') ? true : false
                  return <div key={id} className={`flex-1 h-1.5 rounded-full transition ${active||done?'bg-indigo-500':'bg-zinc-800'}`} title={label} />
                })}
              </div>
              <div className="mt-1 flex justify-between text-[10px] tracking-widest text-zinc-600">
                <span>Planning</span><span>Searching</span><span>Reading</span><span>Analyzing</span><span>Verifying</span><span>Writing</span>
              </div>

              <div className="mt-4 space-y-2 max-h-[62vh] lg:max-h-[62vh] overflow-auto pr-1">
                {events.length===0 && <div className="text-sm text-zinc-500 flex gap-2"><Loader2 className="w-4 h-4 animate-spin"/> Initializing agent-reach (Exa + Jina) • Gemini-style planner...</div>}
                {events.map((ev,i)=>{
                  const iconMap = {
                    stage: <FileText className="w-3.5 h-3.5 mt-0.5 text-white/80 shrink-0"/>,
                    thinking: <Brain className="w-3.5 h-3.5 mt-0.5 text-violet-400 shrink-0"/>,
                    searching: <Globe className="w-3.5 h-3.5 mt-0.5 text-indigo-400 shrink-0"/>,
                    reading: <FileText className="w-3.5 h-3.5 mt-0.5 text-sky-400 shrink-0"/>,
                    fetched: <Check className="w-3.5 h-3.5 mt-0.5 text-emerald-400 shrink-0"/>,
                    analyzing: <Brain className="w-3.5 h-3.5 mt-0.5 text-amber-400 shrink-0"/>,
                    gap_analysis: <Brain className="w-3.5 h-3.5 mt-0.5 text-amber-400 shrink-0"/>,
                    synthesizing: <FileText className="w-3.5 h-3.5 mt-0.5 text-amber-400 shrink-0"/>,
                  }
                  const bgMap = {
                    stage: 'bg-zinc-900 border-zinc-800',
                    thinking: 'bg-violet-500/10 border-violet-500/20',
                    searching: 'bg-indigo-500/10 border-indigo-500/20',
                    reading: 'bg-sky-500/10 border-sky-500/20',
                    fetched: 'bg-zinc-900 border-zinc-800',
                    analyzing: 'bg-amber-500/10 border-amber-500/20',
                    gap_analysis: ev.data.need_more ? 'bg-amber-500/10 border-amber-500/30' : 'bg-emerald-500/10 border-emerald-500/20',
                    synthesizing: 'bg-amber-500/10 border-amber-500/20',
                  }
                  // Special rendering for gap_analysis
                  if(ev.type==='gap_analysis'){
                    return (
                      <div key={i} className={`text-xs p-3 rounded-xl flex gap-2.5 border ${bgMap[ev.type]}`}>
                        {iconMap[ev.type]}
                        <div className="min-w-0 flex-1">
                          <div className="font-medium text-zinc-200">Gap Analysis • Coverage {ev.data.coverage}% {ev.data.need_more?'↻ needs more':'✓ sufficient'}</div>
                          <div className="text-zinc-400 break-words leading-relaxed">{ev.data.reason}</div>
                          {ev.data.gaps?.length>0 && <div className="text-zinc-500 text-[11px] mt-1">Gaps: {ev.data.gaps.join(' • ')}</div>}
                          {ev.data.next_queries?.length>0 && <div className="text-indigo-300 text-[11px] mt-1">Next: {ev.data.next_queries.join(', ')}</div>}
                        </div>
                      </div>
                    )
                  }
                  if(ev.type==='stage'){
                    return (
                      <div key={i} className={`text-xs p-2.5 rounded-xl flex gap-2.5 border ${bgMap[ev.type]} opacity-90`}>
                        <div className="w-1.5 h-1.5 rounded-full bg-white mt-1.5 shrink-0"/>
                        <div className="min-w-0 flex-1">
                          <div className="font-semibold text-zinc-200 uppercase tracking-widest text-[11px]">{ev.data.stage}</div>
                          <div className="text-zinc-400 break-words leading-relaxed">{ev.data.msg}</div>
                        </div>
                      </div>
                    )
                  }
                  return (
                    <div key={i} className={`text-xs p-3 rounded-xl flex gap-2.5 border ${bgMap[ev.type] || 'bg-zinc-900 border-zinc-800'}`}>
                      {iconMap[ev.type] || <FileText className="w-3.5 h-3.5 mt-0.5 text-zinc-500 shrink-0"/>}
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-zinc-200 capitalize">{ev.type.replace('_',' ')}{ev.data.iteration!==undefined?` • iter ${ev.data.iteration+1}`:''}</div>
                        <div className="text-zinc-400 break-words leading-relaxed">{ev.data.msg || ev.data.query || JSON.stringify(ev.data).slice(0,260)}</div>
                        {ev.data.sources && <div className="text-zinc-500 text-[11px] mt-1">{ev.data.sources.length} sources • {ev.data.sources.filter(s=>s.authority==='high').length} high-authority</div>}
                      </div>
                    </div>
                  )
                })}
              </div>
              {events.some(e=>e.type==='synthesizing' || (e.type==='stage' && e.data.stage==='writing')) && <div className="mt-4 text-xs text-amber-400 flex gap-2 items-center"><Loader2 className="w-3 h-3 animate-spin"/> Synthesizing professional report with citations...</div>}
            </div>
          ) : (
            <div className="p-4 lg:p-8 max-w-[880px] mx-auto">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
                <h2 className="text-lg lg:text-xl font-bold text-white">Professional Report</h2>
                <div className="flex flex-wrap items-center gap-2">
                  <button onClick={()=>navigator.clipboard.writeText(report)} className="text-xs px-3.5 py-1.5 rounded-full border border-zinc-700 bg-zinc-900 hover:bg-zinc-800 hover:text-white transition">Copy Markdown</button>
                  <button onClick={()=>downloadFile('md')} disabled={downloading==='md'} className="inline-flex items-center gap-1.5 text-xs px-3.5 py-1.5 rounded-full border border-zinc-700 bg-zinc-900 hover:bg-zinc-800 hover:text-white transition disabled:opacity-50">
                    {downloading==='md' ? <Loader2 className="w-3 h-3 animate-spin"/> : <Download className="w-3 h-3"/>} .MD
                  </button>
                  <button onClick={()=>downloadFile('pdf')} disabled={downloading==='pdf'} className="inline-flex items-center gap-1.5 text-xs px-3.5 py-1.5 rounded-full border border-red-900/60 bg-red-950/40 text-red-200 hover:bg-red-900/40 transition disabled:opacity-50">
                    {downloading==='pdf' ? <Loader2 className="w-3 h-3 animate-spin"/> : <FileDown className="w-3 h-3"/>} PDF
                  </button>
                  <button onClick={()=>downloadFile('docx')} disabled={downloading==='docx'} className="inline-flex items-center gap-1.5 text-xs px-3.5 py-1.5 rounded-full bg-indigo-600 text-white hover:bg-indigo-500 transition disabled:opacity-50">
                    {downloading==='docx' ? <Loader2 className="w-3 h-3 animate-spin"/> : <FileTextIcon className="w-3 h-3"/>} Word
                  </button>
                </div>
              </div>
              <MarkdownRenderer content={report} />
            </div>
          )}
        </div>

        {/* Sources — right */}
        <div className={`${mobileTab!=='sources'?'hidden xl:flex':''} flex-col border-zinc-800 bg-zinc-950 xl:border-l min-h-0 xl:sticky xl:top-[65px] xl:h-[calc(100vh-65px)] xl:overflow-y-auto`}>
          <div className="p-4">
            <h3 className="text-[11px] tracking-[0.12em] text-zinc-500 font-semibold mb-3">SOURCES • {sources.length}</h3>
            <div className="space-y-2.5">
              {sources.map((s,i)=>(
                <a key={i} href={s.url} target="_blank" rel="noopener noreferrer" className="block rounded-xl border border-zinc-800 bg-zinc-900 p-3 hover:border-zinc-700 hover:bg-zinc-800/50 transition group">
                  <div className="text-xs font-medium text-white leading-snug break-words line-clamp-2 group-hover:text-indigo-200">{i+1}. {s.title || s.url}</div>
                  <div className="text-[11px] text-indigo-400/70 break-all leading-tight mt-1 flex gap-1 items-start"><span className="break-all flex-1 min-w-0">{s.url}</span> <ExternalLink className="w-3 h-3 shrink-0 mt-0.5 opacity-60 group-hover:opacity-100"/></div>
                  {s.snippet && <div className="text-[11px] leading-relaxed text-zinc-400 mt-1.5 break-words line-clamp-3">{s.snippet}</div>}
                  <div className="text-[10px] text-zinc-600 mt-1.5 break-words">{s.qid} • {(s.question||'').slice(0,50)}</div>
                </a>
              ))}
              {sources.length===0 && <div className="text-xs text-zinc-600 leading-relaxed">Sources will appear as browsing progresses via agent-reach.</div>}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
