import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeHighlight from 'rehype-highlight'
import rehypeRaw from 'rehype-raw'
import { useState, useMemo } from 'react'
import { Copy, Check } from 'lucide-react'
import { normalizeMarkdown } from '../lib/normalizeMarkdown'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github-dark.css'

function CodeBlock({children, className, ...props}) {
  const [copied, setCopied] = useState(false)
  const code = String(children).replace(/\n$/, '')
  const lang = className?.replace('language-','') || 'text'
  const isBlock = code.includes('\n') || className

  if (!isBlock) {
    return <code className="px-1.5 py-0.5 rounded-md bg-zinc-900 border border-zinc-800 text-[13px] font-mono text-amber-300 break-words" {...props}>{children}</code>
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(()=>setCopied(false), 1800)
  }

  return (
    <div className="my-6 rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-zinc-800/50 border-b border-zinc-800">
        <span className="text-xs font-mono text-zinc-400 lowercase tracking-wide">{lang}</span>
        <button onClick={handleCopy} className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 transition">
          {copied ? <><Check className="w-3 h-3 text-emerald-400"/> Copied</> : <><Copy className="w-3 h-3"/> Copy</>}
        </button>
      </div>
      <pre className="m-0 p-4 overflow-x-auto bg-transparent">
        <code className={className} {...props}>{children}</code>
      </pre>
    </div>
  )
}

// Citations like [1][2] → styled badges
function CitationText({children}) {
  // children is a text string, we parse citations
  const text = String(children)
  const parts = text.split(/(\[\d+(?:,\s*\d+)*\]|\[\d+-\d+\])/g)
  if (parts.length === 1) return <>{children}</>
  return (
    <>
      {parts.map((part, i) => {
        if (/^\[\d/.test(part)) {
          return (
            <span key={i} className="inline-flex items-center mx-0.5">
              {part.match(/\d+/g)?.map((num, j) => (
                <a
                  key={j}
                  href={`#ref-${num}`}
                  className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 mx-0.5 text-[11px] font-medium bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 rounded-full hover:bg-indigo-500/25 hover:text-indigo-200 transition no-underline"
                  title={`Go to source ${num}`}
                  onClick={(e)=>{
                    e.preventDefault()
                    document.getElementById(`ref-${num}`)?.scrollIntoView({behavior:'smooth', block:'center'})
                    document.getElementById(`ref-${num}`)?.classList.add('ring-2','ring-indigo-500/50')
                    setTimeout(()=>document.getElementById(`ref-${num}`)?.classList.remove('ring-2','ring-indigo-500/50'), 2000)
                  }}
                >
                  {num}
                </a>
              ))}
            </span>
          )
        }
        return <span key={i}>{part}</span>
      })}
    </>
  )
}

export default function MarkdownRenderer({ content }) {
  // Repair common LLM malformations (inline bullet runs, tables glued to
  // paragraphs) so remark-gfm opens real lists/tables instead of raw pipes.
  const safeContent = useMemo(() => normalizeMarkdown(content || ''), [content]);
  if (!safeContent.trim()) {
    return <div className="text-zinc-500 italic text-sm py-8 text-center">No report yet — generating...</div>
  }

  return (
    <div className="markdown-renderer">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, rehypeKatex, rehypeHighlight]}
        components={{
          a: ({href, children}) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 underline decoration-indigo-500/30 hover:decoration-indigo-400 underline-offset-2 break-words">
              {children}
            </a>
          ),
          h1: ({children}) => <h1 className="text-[28px] font-bold tracking-tight text-white mt-10 mb-4 leading-tight">{children}</h1>,
          h2: ({children}) => <h2 className="text-[20px] font-bold text-white mt-10 mb-4 pb-3 border-b border-zinc-800 leading-tight">{children}</h2>,
          h3: ({children}) => <h3 className="text-[17px] font-semibold text-white mt-8 mb-3 leading-snug">{children}</h3>,
          h4: ({children}) => <h4 className="text-[15px] font-semibold text-zinc-100 mt-6 mb-2">{children}</h4>,
          p: ({children}) => {
            // Check if children is pure text with citations
            if (typeof children === 'string' || (Array.isArray(children) && children.every(c=>typeof c==='string'))) {
              const text = Array.isArray(children) ? children.join('') : children
              if (/\[\d+\]/.test(text)) {
                return <p className="my-4 leading-7 text-[15px] text-zinc-300 break-words"><CitationText>{text}</CitationText></p>
              }
            }
            return <p className="my-4 leading-7 text-[15px] text-zinc-300 break-words">{children}</p>
          },
          li: ({children}) => {
            // Handle citation in list items too
            const flat = Array.isArray(children) ? children : [children]
            const text = flat.map(c=> typeof c==='string' ? c : '').join('')
            if (/\[\d+\]/.test(text) && flat.every(c=>typeof c==='string')) {
              return <li className="my-1.5 leading-7 text-zinc-300"><CitationText>{text}</CitationText></li>
            }
            return <li className="my-1.5 leading-7 text-zinc-300">{children}</li>
          },
          ul: ({children}) => <ul className="my-4 pl-6 list-disc space-y-1 marker:text-zinc-500">{children}</ul>,
          ol: ({children}) => <ol className="my-4 pl-6 list-decimal space-y-1 marker:text-zinc-500">{children}</ol>,
          blockquote: ({children}) => (
            <blockquote className="my-6 border-l-[3px] border-indigo-500/40 pl-5 py-3 bg-zinc-900/40 rounded-r-xl text-zinc-400 italic leading-relaxed">
              {children}
            </blockquote>
          ),
          table: ({children}) => (
            <div className="my-7 overflow-x-auto rounded-xl border border-zinc-800 -mx-1">
              <table className="w-full text-sm border-collapse min-w-[640px]">{children}</table>
            </div>
          ),
          thead: ({children}) => <thead className="bg-zinc-900">{children}</thead>,
          th: ({children}) => <th className="px-4 py-3 text-left font-semibold text-zinc-200 border-b border-zinc-800 whitespace-nowrap text-xs uppercase tracking-wider bg-zinc-900">{children}</th>,
          td: ({children}) => <td className="px-4 py-3 border-b border-zinc-800/50 align-top text-zinc-300 text-[13px] leading-relaxed break-words">{children}</td>,
          tr: ({children}) => <tr className="even:bg-zinc-900/20 hover:bg-zinc-900/30 transition">{children}</tr>,
          code: CodeBlock,
          pre: ({children}) => <>{children}</>, // handled by code
          hr: () => <hr className="my-8 border-zinc-800" />,
          img: ({src, alt}) => <img src={src} alt={alt} className="rounded-xl border border-zinc-800 my-6 max-w-full h-auto" loading="lazy" />,
          strong: ({children}) => <strong className="font-semibold text-white">{children}</strong>,
          em: ({children}) => <em className="italic text-zinc-300">{children}</em>,
        }}
      >
        {safeContent}
      </ReactMarkdown>
    </div>
  )
}
