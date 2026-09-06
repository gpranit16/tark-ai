import { useEffect, useState } from 'react';
import clsx from 'clsx';

const STEPS = [
  { key: 'research_started',         label: 'Starting research...',     icon: '🔬' },
  { key: 'research_planning',        label: 'Planning research...',      icon: '🧠' },
  { key: 'research_plan_created',    label: 'Research plan ready',       icon: '📋' },
  { key: 'research_task_started',    label: 'Researching sources...',    icon: '🌐' },
  { key: 'research_evidence_collected', label: 'Evidence collected',     icon: '📚' },
  { key: 'research_verification_started', label: 'Verifying evidence...', icon: '🔍' },
  { key: 'research_verification_complete', label: 'Evidence verified',   icon: '✅' },
  { key: 'research_retry',           label: 'Refining research...',      icon: '🔄' },
  { key: 'research_synthesis_started', label: 'Synthesizing answer...', icon: '⚡' },
  { key: 'research_complete',        label: 'Research complete',         icon: '🎯' },
];

export default function ResearchProgress({ events = [], isActive = false }) {
  const [activeTasks, setActiveTasks] = useState([]);
  const [stats, setStats] = useState({ sources: 0, confidence: 0, duration: 0 });
  const [currentStep, setCurrentStep] = useState(null);
  const [plan, setPlan] = useState(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    events.forEach(evt => {
      const { type, data } = evt;

      switch (type) {
        case 'research_plan_created':
          setPlan(data);
          break;
        case 'research_task_started':
          setActiveTasks(prev => [
            ...prev.filter(t => t.task_id !== data.task_id),
            { task_id: data.task_id, query: data.query, agent_type: data.agent_type, status: 'running' },
          ]);
          break;
        case 'research_task_completed':
          setActiveTasks(prev =>
            prev.map(t => t.task_id === data.task_id ? { ...t, status: 'done', evidence_count: data.evidence_count } : t)
          );
          break;
        case 'research_task_failed':
          setActiveTasks(prev =>
            prev.map(t => t.task_id === data.task_id ? { ...t, status: 'failed', error: data.error } : t)
          );
          break;
        case 'research_evidence_collected':
          setStats(s => ({ ...s, sources: data.total_sources }));
          break;
        case 'research_verification_complete':
          setStats(s => ({ ...s, confidence: Math.round((data.confidence || 0) * 100) }));
          break;
        case 'research_retry':
          setRetryCount(data.retry_count);
          break;
        case 'research_complete':
          setStats({ sources: data.source_count, confidence: Math.round((data.confidence || 0) * 100), duration: Math.round(data.duration_ms / 1000) });
          break;
      }

      const step = STEPS.find(s => s.key === type);
      if (step) setCurrentStep(step);
    });
  }, [events]);

  if (!isActive && events.length === 0) return null;

  const agentIcon = (type) => ({ web: '🌐', document: '📄', finance: '💹' }[type] || '🔧');

  return (
    <div className="my-3 rounded-xl border border-accent/25 bg-[#101011] overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 py-2.5 border-b border-white/[0.05] bg-[#141415]">
        <span className="text-xs font-semibold text-accent flex items-center gap-1.5">
          <span>🔬</span> Deep Research
        </span>
        {isActive && (
          <span className="ml-auto flex items-center gap-1.5 text-[11px] text-[#A0A0A0]">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
            Running
          </span>
        )}
        {!isActive && stats.duration > 0 && (
          <span className="ml-auto text-[11px] text-[#A0A0A0]">
            Completed in {stats.duration}s · {stats.sources} sources · {stats.confidence}% confidence
          </span>
        )}
      </div>

      {/* Current step indicator */}
      {currentStep && (
        <div className="px-4 py-2 flex items-center gap-2 text-sm">
          <span>{currentStep.icon}</span>
          <span className={clsx("text-[13px]", isActive ? "text-[#F4F2ED]" : "text-[#A0A0A0]")}>
            {currentStep.label}
          </span>
          {retryCount > 0 && (
            <span className="ml-auto text-[11px] text-accent border border-accent/30 px-2 py-0.5 rounded-full">
              Retry {retryCount}
            </span>
          )}
        </div>
      )}

      {/* Research plan summary */}
      {plan && plan.task_count > 0 && (
        <div className="px-4 pb-2">
          <div className="text-[11px] text-[#767676] mb-1.5">
            Researching {plan.task_count} topics in parallel
          </div>
        </div>
      )}

      {/* Active tasks */}
      {activeTasks.length > 0 && (
        <div className="px-4 pb-3 space-y-1.5">
          {activeTasks.slice(-6).map((task) => (
            <div
              key={task.task_id}
              className={clsx(
                "flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-[12px] border transition-all",
                task.status === 'running'
                  ? "bg-[#18181D] border-accent/30 text-[#E7CA82] animate-pulse"
                  : task.status === 'done'
                  ? "bg-emerald-950/30 border-emerald-800/30 text-emerald-300"
                  : "bg-rose-950/30 border-rose-800/30 text-rose-300"
              )}
            >
              <span>{agentIcon(task.agent_type)}</span>
              <span className="flex-1 truncate text-[11px]">{task.query}</span>
              {task.status === 'running' && <span className="text-[10px] text-[#A0A0A0] shrink-0">searching…</span>}
              {task.status === 'done' && <span className="text-[10px] shrink-0">✓ {task.evidence_count} found</span>}
              {task.status === 'failed' && <span className="text-[10px] shrink-0">✕ failed</span>}
            </div>
          ))}
        </div>
      )}

      {/* Stats bar when complete */}
      {!isActive && stats.sources > 0 && (
        <div className="px-4 pb-3 flex items-center gap-4 text-[11px] text-[#A0A0A0]">
          <span>📚 {stats.sources} sources</span>
          <span>🎯 {stats.confidence}% confidence</span>
          <span>⏱ {stats.duration}s</span>
        </div>
      )}
    </div>
  );
}
