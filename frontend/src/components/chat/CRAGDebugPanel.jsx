import React, { useState } from 'react';
import { Activity, ChevronDown, ChevronRight, CheckCircle2, Circle, Clock, Zap, ShieldCheck, RefreshCw, FileSearch } from 'lucide-react';

export default function CRAGDebugPanel({ ragMeta, latency }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!ragMeta && !latency) return null;

  const retrieved = ragMeta?.retrieved ?? ragMeta?.retrieval?.retrieved ?? 0;
  const reranked = ragMeta?.reranked ?? ragMeta?.retrieval?.reranked ?? 0;
  const confidence = ragMeta?.confidence ?? ragMeta?.retrieval?.confidence ?? 0;
  const attempts = ragMeta?.attempts ?? ragMeta?.crag?.attempts ?? 1;
  const rewritten = ragMeta?.rewritten ?? ragMeta?.crag?.rewritten ?? false;
  const decision = ragMeta?.decision ?? ragMeta?.crag?.final_decision ?? 'grounded';
  const rerankerUsed = ragMeta?.reranker_used ?? ragMeta?.retrieval?.reranker_used ?? (latency?.rerank_time_ms > 0);

  const l = latency || ragMeta?.latency || {};
  const totalMs = l.total_time_ms ?? 0;
  const retMs = l.retrieval_time_ms ?? 0;
  const rrMs = l.rerank_time_ms ?? 0;
  const grMs = l.grader_time_ms ?? 0;
  const rwMs = l.rewrite_time_ms ?? 0;
  const genMs = l.generation_time_ms ?? 0;

  const isFastPath = !rerankerUsed && confidence >= 0.65;

  let scopeName = ragMeta?.scope || ragMeta?.retrieval?.scope;
  if (Array.isArray(scopeName)) {
    scopeName = scopeName.join(', ');
  } else if (!scopeName && ragMeta?.citations && ragMeta.citations.length > 0) {
    const uniqueFilenames = Array.from(new Set(ragMeta.citations.map((c) => c.filename || (c.reference ? c.reference.split(' p.')[0] : null)).filter(Boolean)));
    if (uniqueFilenames.length > 0) {
      scopeName = uniqueFilenames.join(', ');
    }
  }
  const fileCount = ragMeta?.file_count || ragMeta?.retrieval?.file_count || (scopeName ? (scopeName.split(',').length) : null);

  return (
    <div className="mt-2.5 rounded-lg border border-border/60 bg-surface/40 text-xs overflow-hidden transition-all">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3 py-1.5 text-muted-foreground hover:text-gray-200 hover:bg-surface2/50 transition-colors"
      >
        <div className="flex items-center gap-1.5 font-medium">
          <Activity size={13} className={isFastPath ? "text-emerald-400" : "text-accent"} />
          <span className="font-mono text-[11px] text-gray-300">CRAG Pipeline</span>
          {isFastPath && (
            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.2 text-[9px] font-semibold bg-emerald-500/15 text-emerald-400 rounded border border-emerald-500/25">
              <Zap size={9} /> Fast Path
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {totalMs > 0 && (
            <span className="font-mono text-[10px] text-muted-foreground">
              {Math.round(totalMs)}ms
            </span>
          )}
          {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </div>
      </button>

      {isOpen && (
        <div className="px-3 py-2.5 border-t border-border/40 bg-background/30 space-y-2 font-mono text-[11px]">
          {/* Stage 1: Retrieval */}
          <div className="space-y-0.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-gray-300">
                <CheckCircle2 size={12} className="text-emerald-400" />
                <span>Retrieval</span>
              </div>
              <span className="text-muted-foreground">
                {retMs > 0 ? `${retMs.toFixed(1)}ms` : '✓'} ({retrieved} chunks)
              </span>
            </div>
            {scopeName && (
              <div className="pl-4 text-[10px] text-muted-foreground/80 flex items-center justify-between">
                <span>Scope: <span className="text-emerald-400/90">{scopeName}</span></span>
                {fileCount && <span>Files: {fileCount}</span>}
              </div>
            )}
          </div>

          {/* Stage 2: Confidence */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-gray-300">
              <CheckCircle2 size={12} className="text-emerald-400" />
              <span>Confidence</span>
            </div>
            <span className={confidence >= 0.65 ? "text-emerald-400 font-semibold" : "text-amber-400 font-semibold"}>
              {(confidence * 100).toFixed(0)}% ({confidence.toFixed(2)})
            </span>
          </div>

          {/* Stage 3: Reranker */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-gray-300">
              {rerankerUsed ? (
                <CheckCircle2 size={12} className="text-accent" />
              ) : (
                <Circle size={12} className="text-muted-foreground/60" />
              )}
              <span>Reranker</span>
            </div>
            <span className={rerankerUsed ? "text-accent" : "text-muted-foreground/70"}>
              {rerankerUsed ? (rrMs > 0 ? `${rrMs.toFixed(1)}ms (${reranked} chunks)` : `Executed (${reranked})`) : 'Skipped (Fast Path)'}
            </span>
          </div>

          {/* Stage 4: Query Rewrite */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-gray-300">
              {rewritten ? (
                <RefreshCw size={12} className="text-amber-400" />
              ) : (
                <Circle size={12} className="text-muted-foreground/60" />
              )}
              <span>Rewrite</span>
            </div>
            <span className={rewritten ? "text-amber-400" : "text-muted-foreground/70"}>
              {rewritten ? (rwMs > 0 ? `${rwMs.toFixed(1)}ms` : 'Rewritten') : 'Skipped'}
            </span>
          </div>

          {/* Stage 5: Retry */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-gray-300">
              {attempts > 1 ? (
                <CheckCircle2 size={12} className="text-accent" />
              ) : (
                <Circle size={12} className="text-muted-foreground/60" />
              )}
              <span>Retry</span>
            </div>
            <span className={attempts > 1 ? "text-accent" : "text-muted-foreground/70"}>
              {attempts > 1 ? `Attempt ${attempts}` : 'Skipped'}
            </span>
          </div>

          {/* Stage 6: Generation */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-gray-300">
              <CheckCircle2 size={12} className="text-emerald-400" />
              <span>Generation</span>
            </div>
            <span className="text-muted-foreground">
              {genMs > 0 ? `${genMs.toFixed(1)}ms` : '✓'}
            </span>
          </div>

          {/* Summary footer */}
          <div className="pt-2 mt-1 border-t border-border/30 flex items-center justify-between text-[10px] text-muted-foreground">
            <span>Decision: <span className="text-gray-200 capitalize">{decision.replace('_', ' ')}</span></span>
            {totalMs > 0 && <span>Total: <span className="text-emerald-400 font-semibold">{totalMs.toFixed(1)}ms</span></span>}
          </div>
        </div>
      )}
    </div>
  );
}
