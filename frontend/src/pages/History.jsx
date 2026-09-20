import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { Trash2 } from 'lucide-react'
export default function History(){
  const [items,setItems]=useState([])
  const [err,setErr]=useState('')
  useEffect(()=>{ api('/api/history').then(setItems).catch(e=>setErr(String(e.message))) },[])
  async function del(id){
    await api(`/api/history/${id}`,{method:'DELETE'})
    setItems(items.filter(i=>i.job_id!==id))
  }
  return (
    <div className="max-w-[900px] mx-auto p-8">
      <h1 className="text-2xl font-bold">History</h1>
      <p className="text-zinc-500 text-sm mt-1">Past deep researches — persisted in SQLite</p>
      {err && <div className="mt-4 rounded-xl border border-red-900 bg-red-950/30 p-3 text-sm text-red-300">{err}</div>}
      <div className="mt-6 space-y-2">
        {items.map(it=>(
          <div key={it.job_id} className="flex items-center justify-between p-4 rounded-xl border border-zinc-800 bg-zinc-900/50">
            <Link to={`/research/${it.job_id}`} className="min-w-0">
              <div className="font-medium text-sm truncate">{it.query}</div>
              <div className="text-xs text-zinc-500">{it.job_id} • {it.depth} • {it.status} • {new Date(it.created_at).toLocaleString()}</div>
            </Link>
            <button onClick={()=>del(it.job_id)} className="p-2 hover:bg-zinc-800 rounded-lg text-zinc-500 hover:text-red-400"><Trash2 className="w-4 h-4"/></button>
          </div>
        ))}
        {items.length===0 && <div className="text-sm text-zinc-600">No researches yet.</div>}
      </div>
    </div>
  )
}
