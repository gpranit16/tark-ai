import { useState } from 'react';
import { Code2, FileCode, CheckCircle2, ChevronDown, ChevronUp, Cpu, Sparkles } from 'lucide-react';
import clsx from 'clsx';

export default function CodingProgress({ events = [], isActive = false }) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!events || events.length === 0) return null;

  // Extract events
  const startedEvent = events.find((e) => e.type === 'coding_started')?.data;
  const filesLoaded = events.filter((e) => e.type === 'coding_file').map((e) => e.data);
  const contextReady = events.find((e) => e.type === 'coding_context_ready')?.data;
  const generationEvent = events.find((e) => e.type === 'coding_generation')?.data;
  const completeEvent = events.find((e) => e.type === 'coding_complete')?.data;
  const errorEvent = events.find((e) => e.type === 'coding_error')?.data;

  // Determine current status string
  let statusText = 'Initializing Coding Workspace…';
  if (errorEvent) {
    statusText = `Error: ${errorEvent.error}`;
  } else if (completeEvent) {
    statusText = `Analysis Complete · ${filesLoaded.length} files scanned`;
  } else if (generationEvent) {
    statusText = `Generating solution using ${generationEvent.model || 'model'}…`;
  } else if (contextReady) {
    statusText = `Context Ready · ${contextReady.total_files} files loaded (${Math.round(contextReady.total_chars / 4)} tokens)`;
  } else if (filesLoaded.length > 0) {
    statusText = `Reading ${filesLoaded[filesLoaded.length - 1].filename}…`;
  }

  return (
    <div className="mb-4 rounded-xl border border-white/[0.06] bg-[#101011] overflow-hidden text-xs shadow-sm">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3.5 py-2.5 bg-[#141415] border-b border-white/[0.05]">
        <div className="flex items-center gap-2.5 truncate">
          <div className={clsx(
            "w-5 h-5 rounded flex items-center justify-center text-xs",
            isActive ? "bg-accent/20 text-accent animate-pulse" : "bg-[#101011] text-[#767676]"
          )}>
            <Code2 size={13} />
          </div>

          <div className="flex items-center gap-2 truncate">
            <span className="font-semibold text-[#F4F2ED]">Coding Workspace</span>
            <span className="text-[#767676]">•</span>
            <span className="text-[#A0A0A0] truncate">{statusText}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {filesLoaded.length > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-[#101011] text-[#F4F2ED] font-mono text-[10px] border border-white/[0.06]">
              {filesLoaded.length} {filesLoaded.length === 1 ? 'file' : 'files'}
            </span>
          )}

          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 text-[#767676] hover:text-[#F4F2ED] rounded hover:bg-[#141415] transition-colors"
            title={isExpanded ? 'Collapse files list' : 'View loaded files'}
          >
            {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
        </div>
      </div>

      {/* Expanded File Details */}
      {isExpanded && (
        <div className="p-3 bg-[#080808] space-y-2 border-t border-white/[0.05]">
          {filesLoaded.length > 0 ? (
            <div className="space-y-1.5">
              <div className="text-[11px] font-semibold text-[#767676] uppercase tracking-wider">
                Loaded Codebase Context:
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                {filesLoaded.map((file, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between px-2.5 py-1.5 rounded bg-[#101011] border border-white/[0.06] text-[#F4F2ED]"
                  >
                    <div className="flex items-center gap-1.5 truncate">
                      <FileCode size={12} className="text-accent shrink-0" />
                      <span className="font-mono text-xs truncate">{file.filename}</span>
                    </div>
                    <span className="text-[10px] font-mono text-[#767676] shrink-0 ml-2">
                      {file.language} · {Math.round((file.size_bytes || 0) / 1024 * 10) / 10}KB
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-[#767676] italic text-[11px]">
              No standalone files attached. Using conversation history and workspace context.
            </div>
          )}

          {completeEvent && (
            <div className="pt-2 border-t border-white/[0.05] flex items-center justify-between text-[#A0A0A0] text-[11px]">
              <div className="flex items-center gap-1.5 text-emerald-400">
                <CheckCircle2 size={12} />
                <span>Suggested changes generated successfully</span>
              </div>
              <span className="text-[10px] font-mono">
                {completeEvent.changes_count || 0} patches suggested
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
