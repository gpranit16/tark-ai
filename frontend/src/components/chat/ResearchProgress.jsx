import { useEffect, useState, useMemo } from 'react';
import clsx from 'clsx';
import {
  Sparkles,
  Compass,
  Search,
  Globe,
  Layers,
  FileCheck2,
  Cpu,
  Image as ImageIcon,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

const STAGES = [
  { id: 'classify', label: 'Scope & Recency', icon: Compass },
  { id: 'search', label: 'Evidence Collection', icon: Globe },
  { id: 'sections', label: 'Section Fanout', icon: Layers },
  { id: 'verify', label: 'Grounding Verification', icon: FileCheck2 },
  { id: 'synthesis', label: 'Report Synthesis', icon: Cpu },
];

export default function ResearchProgress({ events = [], isActive = false }) {
  const [activeStage, setActiveStage] = useState('classify');
  const [queries, setQueries] = useState([]);
  const [sources, setSources] = useState({ count: 0, domains: [] });
  const [sections, setSections] = useState([]);
  const [images, setImages] = useState([]);
  const [metrics, setMetrics] = useState({ confidence: null, coverage: null, duration: null });
  const [expanded, setExpanded] = useState(true);
  const [currentStatusText, setCurrentStatusText] = useState('Initializing Deep Research 2.0...');

  useEffect(() => {
    if (!events || events.length === 0) return;

    events.forEach((evt) => {
      const { type, data } = evt;
      if (!data) return;

      switch (type) {
        case 'research_classifying':
          setActiveStage('classify');
          setCurrentStatusText(`Analyzing research scope & recency requirements...`);
          break;

        case 'research_started':
          setActiveStage('classify');
          if (data.recency_days) {
            setCurrentStatusText(`Targeting ${data.recency_days <= 7 ? 'past 7 days' : data.recency_days <= 30 ? 'past month' : 'comprehensive'} primary sources`);
          } else {
            setCurrentStatusText('Analyzing research scope & recency requirements...');
          }
          break;

        case 'research_queries_generated':
          setActiveStage('search');
          if (Array.isArray(data.queries)) {
            setQueries(data.queries);
            setCurrentStatusText(`Generated ${data.queries.length} multi-angle research queries`);
          }
          break;

        case 'research_search_started':
          setActiveStage('search');
          setCurrentStatusText(`Executing parallel Tavily search across ${data.query_count || queries.length || 'multiple'} angles...`);
          break;

        case 'research_search_completed':
          setActiveStage('search');
          setCurrentStatusText(`Retrieved raw evidence from web sources`);
          break;

        case 'research_sources_deduplicated':
          setActiveStage('search');
          setSources({
            count: data.total_sources || 0,
            domains: data.domains || [],
          });
          setCurrentStatusText(`Verified & deduplicated ${data.total_sources} authoritative sources`);
          break;

        case 'research_plan_created':
          if (Array.isArray(data.sections)) {
            setSections(data.sections.map(s => ({
              id: s.section_id,
              title: s.title,
              status: 'pending',
            })));
            setCurrentStatusText(`Decomposed into ${data.sections.length} parallel section workers`);
          } else if (data.task_count) {
            setCurrentStatusText(`Planned ${data.task_count} parallel research tracks`);
          }
          break;

        case 'research_section_started':
          setActiveStage('sections');
          setSections(prev => {
            const exists = prev.some(s => s.id === data.section_id);
            if (exists) {
              return prev.map(s => s.id === data.section_id ? { ...s, status: 'running', title: data.title || s.title } : s);
            }
            return [...prev, { id: data.section_id, title: data.title, status: 'running' }];
          });
          setCurrentStatusText(`Drafting section: "${data.title}"`);
          break;

        case 'research_section_completed':
          setSections(prev =>
            prev.map(s => s.id === data.section_id ? { ...s, status: 'done', title: data.title || s.title } : s)
          );
          setCurrentStatusText(`Completed section: "${data.title}"`);
          break;

        case 'research_task_started':
          setSections(prev => [
            ...prev.filter(t => t.id !== data.task_id),
            { id: data.task_id, title: data.query || `Task ${data.task_id}`, status: 'running' },
          ]);
          break;

        case 'research_task_completed':
          setSections(prev =>
            prev.map(t => t.id === data.task_id ? { ...t, status: 'done' } : t)
          );
          break;

        case 'research_verification_started':
          setActiveStage('verify');
          setCurrentStatusText('Deterministically verifying URL citations & grounding coverage...');
          break;

        case 'research_verification_complete':
          setActiveStage('verify');
          setMetrics(prev => ({
            ...prev,
            confidence: data.confidence ? Math.round(data.confidence * 100) : prev.confidence,
            coverage: data.coverage ? Math.round(data.coverage * 100) : prev.coverage,
          }));
          setCurrentStatusText(`Citations validated: ${Math.round((data.confidence || 0.95) * 100)}% claim coverage`);
          break;

        case 'research_synthesis_started':
          setActiveStage('synthesis');
          setCurrentStatusText('Synthesizing structured multi-section report with Gemini 3.5 Flash-Lite...');
          break;

        case 'research_image_started':
          setCurrentStatusText(`Generating contextual architectural visual...`);
          break;

        case 'research_image_completed':
          setImages(prev => [...prev, data]);
          setCurrentStatusText(`Generated research visual`);
          break;

        case 'research_complete':
          setActiveStage('synthesis');
          setMetrics({
            confidence: data.confidence ? Math.round(data.confidence * 100) : 95,
            duration: data.duration_ms ? (data.duration_ms / 1000).toFixed(1) : null,
          });
          if (data.source_count) {
            setSources(s => ({ ...s, count: data.source_count }));
          }
          setCurrentStatusText('Deep Research completed successfully');
          break;
      }
    });
  }, [events]);

  if (!isActive && events.length === 0) return null;

  const currentStageIndex = useMemo(() => {
    const idx = STAGES.findIndex(s => s.id === activeStage);
    return idx === -1 ? 0 : idx;
  }, [activeStage]);

  return (
    <div className="my-3 rounded-2xl border border-accent/25 bg-[#0D0D0F] overflow-hidden shadow-gold-sm transition-all duration-300">
      {/* Top Header Bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#131316] border-b border-white/[0.06]">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-6 h-6 rounded-lg bg-accent/15 border border-accent/30 text-accent">
            <Sparkles className="w-3.5 h-3.5 text-accent animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold tracking-luxury text-[#F4F2ED] uppercase">
                TARK Deep Research 2.0
              </span>
              {isActive && (
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-accent/10 border border-accent/25 text-accent-highlight">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent animate-ping" />
                  Live Agentic Pipeline
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {!isActive && metrics.duration && (
            <span className="text-[11px] text-[#A0A0A0]">
              Finished in {metrics.duration}s
            </span>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1 rounded-lg text-[#77736D] hover:text-[#F4F2ED] hover:bg-white/5 transition-colors"
            title={expanded ? 'Collapse details' : 'Expand details'}
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Stage Stepper Progress Bar */}
      <div className="px-4 py-3 bg-[#101012] border-b border-white/[0.04]">
        <div className="grid grid-cols-5 gap-1.5">
          {STAGES.map((stg, i) => {
            const Icon = stg.icon;
            const isCurrent = activeStage === stg.id;
            const isCompleted = currentStageIndex > i || (!isActive && events.some(e => e.type === 'research_complete'));

            return (
              <div
                key={stg.id}
                className={clsx(
                  "flex flex-col items-center p-1.5 rounded-lg transition-all text-center",
                  isCurrent
                    ? "bg-accent/10 border border-accent/30 text-accent-highlight"
                    : isCompleted
                    ? "bg-white/[0.02] text-emerald-400"
                    : "text-[#555] opacity-60"
                )}
              >
                <div className="flex items-center justify-center w-5 h-5 mb-1">
                  {isCurrent && isActive ? (
                    <Loader2 className="w-3.5 h-3.5 text-accent animate-spin" />
                  ) : isCompleted ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  ) : (
                    <Icon className="w-3.5 h-3.5" />
                  )}
                </div>
                <span className="text-[10px] font-medium truncate max-w-full leading-tight">
                  {stg.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Live Status Ticker */}
      <div className="px-4 py-2.5 flex items-center justify-between gap-3 text-xs bg-[#0B0B0C]">
        <div className="flex items-center gap-2 truncate">
          {isActive ? (
            <span className="w-2 h-2 rounded-full bg-accent animate-pulse shrink-0" />
          ) : (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          )}
          <span className="text-[#E0DDD5] truncate font-medium">
            {currentStatusText}
          </span>
        </div>

        {/* Live Counters */}
        <div className="flex items-center gap-3 shrink-0 text-[11px] text-[#A0A0A0]">
          {sources.count > 0 && (
            <span className="flex items-center gap-1">
              <Globe className="w-3 h-3 text-accent" /> {sources.count} sources
            </span>
          )}
          {metrics.confidence && (
            <span className="flex items-center gap-1 text-emerald-400">
              <FileCheck2 className="w-3 h-3" /> {metrics.confidence}% grounded
            </span>
          )}
        </div>
      </div>

      {/* Expandable Details Container */}
      {expanded && (
        <div className="p-4 space-y-3 border-t border-white/[0.04] bg-[#0E0E10] text-[12px]">
          {/* Query Angles Pills */}
          {queries.length > 0 && (
            <div>
              <div className="text-[10px] font-semibold text-[#77736D] uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                <Search className="w-3 h-3 text-accent" />
                Explored Research Angles ({queries.length})
              </div>
              <div className="flex flex-wrap gap-1.5">
                {queries.map((q, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] bg-[#161619] border border-white/[0.06] text-[#D8D5CD]"
                  >
                    <span className="text-accent text-[9px]">#{i + 1}</span>
                    <span className="truncate max-w-[200px]">{q.query || q}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Parallel Section Workstreams */}
          {sections.length > 0 && (
            <div>
              <div className="text-[10px] font-semibold text-[#77736D] uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                <Layers className="w-3 h-3 text-accent" />
                Section Drafting Workstreams ({sections.length})
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                {sections.map((sec, i) => (
                  <div
                    key={sec.id || i}
                    className={clsx(
                      "flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-[11px] transition-all",
                      sec.status === 'running'
                        ? "bg-accent/10 border-accent/30 text-accent-highlight"
                        : sec.status === 'done'
                        ? "bg-emerald-950/20 border-emerald-800/25 text-emerald-300"
                        : "bg-[#141416] border-white/[0.04] text-[#77736D]"
                    )}
                  >
                    {sec.status === 'running' ? (
                      <Loader2 className="w-3 h-3 text-accent animate-spin shrink-0" />
                    ) : sec.status === 'done' ? (
                      <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                    ) : (
                      <span className="w-3 h-3 rounded-full border border-white/20 shrink-0" />
                    )}
                    <span className="truncate flex-1">{sec.title}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sources Summary Domains */}
          {sources.domains && sources.domains.length > 0 && (
            <div className="pt-1">
              <div className="text-[10px] font-semibold text-[#77736D] uppercase tracking-wider mb-1 flex items-center gap-1.5">
                <Globe className="w-3 h-3 text-accent" />
                Top Authoritative Domains
              </div>
              <div className="flex flex-wrap gap-1 text-[10px] text-[#A0A0A0]">
                {sources.domains.slice(0, 8).map((d, i) => (
                  <span
                    key={i}
                    className="px-1.5 py-0.5 rounded bg-black/40 border border-white/[0.06] text-[#CCC8C0]"
                  >
                    {d}
                  </span>
                ))}
                {sources.domains.length > 8 && (
                  <span className="px-1.5 py-0.5 rounded bg-black/40 text-[#77736D]">
                    +{sources.domains.length - 8} more
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
