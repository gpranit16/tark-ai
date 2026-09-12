import { useState, useRef, useEffect } from 'react';
import { 
  Zap, 
  MessageSquare, 
  Brain, 
  FileText, 
  Search, 
  Code, 
  Cpu, 
  ChevronDown, 
  Check, 
  Sparkles 
} from 'lucide-react';
import clsx from 'clsx';

const MODES = [
  {
    id: 'fast',
    label: 'Fast',
    icon: Zap,
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10',
    description: 'Low latency, quick answers',
  },
  {
    id: 'normal',
    label: 'Normal',
    icon: MessageSquare,
    color: 'text-blue-400',
    bgColor: 'bg-blue-500/10',
    description: 'Balanced chat and reasoning',
  },
  {
    id: 'reasoning',
    label: 'Reasoning',
    icon: Brain,
    color: 'text-purple-400',
    bgColor: 'bg-purple-500/10',
    description: 'Deep multi-step reasoning',
  },
  {
    id: 'rag',
    label: 'RAG (Doc Q&A)',
    icon: FileText,
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/10',
    description: 'Grounded in uploaded documents',
  },
  {
    id: 'deep_research',
    label: 'Deep Research',
    icon: Search,
    color: 'text-[#D4AF37]',
    bgColor: 'bg-[#D4AF37]/10',
    description: 'Multi-step web search & synthesis',
  },
  {
    id: 'coding',
    label: 'Coding',
    icon: Code,
    color: 'text-cyan-400',
    bgColor: 'bg-cyan-500/10',
    description: 'Code generation & repository editing',
  },
];

const MODELS = [
  {
    id: 'qwen/qwen3.8-27b',
    name: 'qwen3.8-27b',
    badge: 'Balanced / Code',
    badgeColor: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
    icon: Cpu,
  },
  {
    id: 'meta/llama-3.2-11b-vision-instruct',
    name: 'Llama 3.2 11B',
    badge: 'NVIDIA Instant (0.7s)',
    badgeColor: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    icon: Zap,
  },
  {
    id: 'nvidia/nemotron-3.5-lightning-30b-a3b',
    name: 'Nemotron 3.5',
    badge: 'NVIDIA 30B',
    badgeColor: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    icon: Sparkles,
  },
  {
    id: 'openai/gpt-oss-120b',
    name: 'gpt-oss-120b',
    badge: 'Deep Reasoning',
    badgeColor: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
    icon: Brain,
  },
  {
    id: 'openai/gpt-oss-20b',
    name: 'gpt-oss-20b',
    badge: 'Fast Reasoning',
    badgeColor: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    icon: Zap,
  },
  {
    id: 'qwen/qwen3.6-27b',
    name: 'qwen3.6-27b',
    badge: 'Fast',
    badgeColor: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    icon: Sparkles,
  },
];

export default function ModeModelSelector({ mode, setMode, model, setModel }) {
  const [isModeOpen, setIsModeOpen] = useState(false);
  const [isModelOpen, setIsModelOpen] = useState(false);

  const modeRef = useRef(null);
  const modelRef = useRef(null);

  // Close dropdowns on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (modeRef.current && !modeRef.current.contains(event.target)) {
        setIsModeOpen(false);
      }
      if (modelRef.current && !modelRef.current.contains(event.target)) {
        setIsModelOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentMode = MODES.find((m) => m.id === mode) || MODES[1];
  const currentModel = MODELS.find((m) => m.id === model) || MODELS[0];
  const CurrentModeIcon = currentMode.icon;
  const CurrentModelIcon = currentModel.icon;

  return (
    <div className="flex items-center gap-1.5 text-xs">
      {/* Mode Selector */}
      <div className="relative" ref={modeRef}>
        <button
          type="button"
          onClick={() => {
            setIsModeOpen(!isModeOpen);
            setIsModelOpen(false);
          }}
          className={clsx(
            'flex items-center gap-1.5 px-2.5 py-1 rounded-lg font-medium transition-all duration-150',
            'bg-[#141415] hover:bg-[#1C1C20] border border-white/[0.06] hover:border-white/[0.12]',
            'text-[#F4F2ED] shadow-sm',
            isModeOpen && 'border-accent/50 ring-1 ring-accent/25 bg-[#18181D]'
          )}
          title="Select Conversation Mode"
        >
          <CurrentModeIcon size={13} className={currentMode.color} />
          <span className="truncate max-w-[120px] text-[11.5px]">{currentMode.label}</span>
          <ChevronDown
            size={12}
            className={clsx('text-[#767676] transition-transform duration-150', isModeOpen && 'rotate-180 text-[#F4F2ED]')}
          />
        </button>

        {isModeOpen && (
          <div className="absolute bottom-full mb-2 left-0 w-64 bg-[#101011] border border-white/[0.08] rounded-xl shadow-2xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-100 backdrop-blur-md">
            <div className="px-2 py-1 mb-1 text-[9.5px] font-semibold tracking-wider text-[#767676] uppercase border-b border-white/[0.05]">
              Conversation Mode
            </div>
            <div className="space-y-0.5">
              {MODES.map((item) => {
                const Icon = item.icon;
                const isSelected = item.id === mode;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setMode(item.id);
                      setIsModeOpen(false);
                    }}
                    className={clsx(
                      'w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-left transition-colors',
                      isSelected
                        ? 'bg-[#18181D] text-accent font-medium border border-accent/30'
                        : 'text-[#A0A0A0] hover:text-[#F4F2ED] hover:bg-[#141415]'
                    )}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className={clsx('p-1.5 rounded-md', item.bgColor)}>
                        <Icon size={14} className={item.color} />
                      </div>
                      <div className="truncate">
                        <div className="text-xs leading-none font-medium mb-0.5">{item.label}</div>
                        <div className="text-[10px] text-[#767676] truncate">{item.description}</div>
                      </div>
                    </div>
                    {isSelected && <Check size={14} className="text-accent shrink-0 ml-2" />}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Model Selector */}
      <div className="relative" ref={modelRef}>
        <button
          type="button"
          onClick={() => {
            setIsModelOpen(!isModelOpen);
            setIsModeOpen(false);
          }}
          className={clsx(
            'flex items-center gap-1.5 px-2.5 py-1 rounded-lg font-medium transition-all duration-150',
            'bg-[#141415] hover:bg-[#1C1C20] border border-white/[0.06] hover:border-white/[0.12]',
            'text-[#F4F2ED] shadow-sm',
            isModelOpen && 'border-accent/50 ring-1 ring-accent/25 bg-[#18181D]'
          )}
          title="Select AI Model"
        >
          <CurrentModelIcon size={13} className="text-accent" />
          <span className="truncate max-w-[130px] font-mono text-[11px]">{currentModel.name}</span>
          <ChevronDown
            size={12}
            className={clsx('text-[#767676] transition-transform duration-150', isModelOpen && 'rotate-180 text-[#F4F2ED]')}
          />
        </button>

        {isModelOpen && (
          <div className="absolute bottom-full mb-2 left-0 w-72 bg-[#101011] border border-white/[0.08] rounded-xl shadow-2xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-100 backdrop-blur-md">
            <div className="px-2 py-1 mb-1 text-[9.5px] font-semibold tracking-wider text-[#767676] uppercase border-b border-white/[0.05]">
              Active Model
            </div>
            <div className="space-y-0.5">
              {MODELS.map((item) => {
                const Icon = item.icon;
                const isSelected = item.id === model;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setModel(item.id);
                      setIsModelOpen(false);
                    }}
                    className={clsx(
                      'w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-left transition-colors',
                      isSelected
                        ? 'bg-[#18181D] text-accent font-medium border border-accent/30'
                        : 'text-[#A0A0A0] hover:text-[#F4F2ED] hover:bg-[#141415]'
                    )}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="p-1.5 rounded-md bg-[#18181D]">
                        <Icon size={14} className="text-[#A0A0A0]" />
                      </div>
                      <div className="truncate">
                        <div className="text-xs font-mono font-medium leading-none mb-1 text-[#F4F2ED]">
                          {item.name}
                        </div>
                        <span className={clsx('inline-block text-[9px] px-1.5 py-0.2 rounded border font-sans', item.badgeColor)}>
                          {item.badge}
                        </span>
                      </div>
                    </div>
                    {isSelected && <Check size={14} className="text-accent shrink-0 ml-2" />}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
