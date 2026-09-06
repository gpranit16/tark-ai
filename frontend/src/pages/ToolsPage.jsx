import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  Wrench,
  Calculator,
  Globe,
  FileText,
  CloudSun,
  Coins,
  DollarSign,
  TrendingUp,
  Newspaper,
  Database,
  Brain,
  MessageSquare,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  Terminal,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';
import clsx from 'clsx';
import { listTools, executeTool } from '../api/toolsApi';
import IntelligenceCore from '../components/IntelligenceCore';

const TOOL_ICONS = {
  calculate: Calculator,
  search_web: Globe,
  read_url: FileText,
  get_weather: CloudSun,
  convert_currency: DollarSign,
  search_news: Newspaper,
  get_stock_price: TrendingUp,
  get_crypto_price: Coins,
  search_knowledge_base: Database,
  search_user_memory: Brain,
  search_conversation_history: MessageSquare,
};

const SAMPLE_INPUTS = {
  calculate: { expression: '(14500 * 0.18) + (350 * 4.5)' },
  search_web: { query: 'latest breakthrough in quantum computing', max_results: 3 },
  read_url: { url: 'https://example.com' },
  get_weather: { location: 'Tokyo' },
  convert_currency: { amount: 250, from_currency: 'USD', to_currency: 'EUR' },
  search_news: { query: 'artificial intelligence open source models', max_results: 3 },
  get_stock_price: { symbol: 'NVDA' },
  get_crypto_price: { symbol: 'BTC', vs_currency: 'USD' },
  search_knowledge_base: { query: 'system architecture design', top_k: 3 },
  search_user_memory: { query: 'user preferences and skills', top_k: 5 },
  search_conversation_history: { query: 'deployment guidelines', max_results: 3 },
};

export default function ToolsPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPermission, setSelectedPermission] = useState('all');
  const [activeTesterTool, setActiveTesterTool] = useState(null);
  const [testerParams, setTesterParams] = useState('{}');
  const [executionResult, setExecutionResult] = useState(null);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['tools-catalog'],
    queryFn: listTools,
  });

  const executeMutation = useMutation({
    mutationFn: async ({ toolName, params }) => {
      let parsed = {};
      try {
        parsed = typeof params === 'string' ? JSON.parse(params) : params;
      } catch (e) {
        throw new Error(`Invalid JSON parameters: ${e.message}`);
      }
      return executeTool(toolName, parsed);
    },
    onSuccess: (result) => {
      setExecutionResult(result);
    },
    onError: (err) => {
      setExecutionResult({
        success: false,
        error: err.message || 'Execution failed',
        data: null,
      });
    },
  });

  const tools = data?.tools || [];

  const filteredTools = tools.filter((tool) => {
    const matchesSearch =
      tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tool.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesPerm = selectedPermission === 'all' || tool.permission.toLowerCase() === selectedPermission.toLowerCase();
    return matchesSearch && matchesPerm;
  });

  const openTester = (tool) => {
    setActiveTesterTool(tool);
    const sample = SAMPLE_INPUTS[tool.name] || {};
    setTesterParams(JSON.stringify(sample, null, 2));
    setExecutionResult(null);
  };

  const runTesterExecution = () => {
    if (!activeTesterTool) return;
    executeMutation.mutate({
      toolName: activeTesterTool.name,
      params: testerParams,
    });
  };

  const getPermissionBadge = (perm) => {
    const p = (perm || '').toUpperCase();
    if (p === 'SAFE') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-950/60 text-emerald-300 border border-emerald-800/40">
          <ShieldCheck className="w-3 h-3" /> SAFE
        </span>
      );
    }
    if (p === 'NETWORK') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-sky-950/60 text-sky-300 border border-sky-800/40">
          <Globe className="w-3 h-3" /> NETWORK
        </span>
      );
    }
    if (p === 'USER_DATA') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-950/60 text-amber-300 border border-amber-800/40">
          <Shield className="w-3 h-3" /> USER DATA
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-rose-950/60 text-rose-300 border border-rose-800/40">
        <ShieldAlert className="w-3 h-3" /> SYSTEM
      </span>
    );
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#121316] text-[#F3EFE0] overflow-y-auto">
      {/* Top Header */}
      <div className="border-b border-[#2A2B30] bg-[#16171B]/80 backdrop-blur px-8 py-6 sticky top-0 z-10">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#C5A880]/20 to-[#A27B5C]/10 border border-[#C5A880]/30 flex items-center justify-center text-[#E5D4B3] shadow-inner">
              <Wrench className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-xl font-semibold text-[#F3EFE0] tracking-tight">Tool Infrastructure</h1>
                <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-[#23252B] text-[#C5A880] border border-[#3A3C45]">
                  {tools.length} Tools Registered
                </span>
              </div>
              <p className="text-xs text-[#9E9A90] mt-0.5">
                Secure, isolated tool registry with AST sandboxing, SSRF validation, and dynamic model orchestration
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="px-3 py-2 text-xs font-medium text-[#C5A880] hover:text-[#F3EFE0] bg-[#1B1C20] hover:bg-[#25272F] border border-[#2A2B30] rounded-lg transition-colors flex items-center gap-1.5"
            >
              <RefreshCw className={clsx('w-3.5 h-3.5', isFetching && 'animate-spin')} />
              Refresh
            </button>
          </div>
        </div>

        {/* Search & Filter Toolbar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 mt-6">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#73716B]" />
            <input
              type="text"
              placeholder="Search tools by name or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-[#1B1C20] border border-[#2A2B30] rounded-lg text-sm text-[#F3EFE0] placeholder-[#73716B] focus:outline-none focus:border-[#C5A880]/50 transition-colors"
            />
          </div>

          <div className="flex items-center gap-1.5 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0">
            {['all', 'safe', 'network', 'user_data'].map((perm) => (
              <button
                key={perm}
                onClick={() => setSelectedPermission(perm)}
                className={clsx(
                  'px-3 py-1.5 rounded-lg text-xs font-medium capitalize whitespace-nowrap transition-colors',
                  selectedPermission === perm
                    ? 'bg-[#C5A880]/20 text-[#E5D4B3] border border-[#C5A880]/40'
                    : 'text-[#9E9A90] hover:text-[#F3EFE0] bg-[#1B1C20] border border-[#2A2B30]'
                )}
              >
                {perm === 'all' ? 'All Permissions' : perm.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="p-8 max-w-7xl w-full mx-auto flex-1">
        {isLoading ? (
          <div className="py-20 text-center space-y-4">
            <IntelligenceCore size="md" active={true} className="mx-auto" />
            <p className="text-xs text-[#767676]">Loading tool catalog...</p>
          </div>
        ) : filteredTools.length === 0 ? (
          <div className="text-center py-16 border border-dashed border-white/[0.08] rounded-2xl bg-[#101011] p-8 space-y-3">
            <IntelligenceCore size="md" className="mx-auto" />
            <h3 className="text-base font-semibold text-[#F4F2ED]">No tools found</h3>
            <p className="text-xs text-[#A0A0A0] mt-1">Try adjusting your search query or permission filter.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredTools.map((tool) => {
              const IconComp = TOOL_ICONS[tool.name] || Wrench;
              return (
                <div
                  key={tool.name}
                  className="bg-[#101011] border border-white/[0.06] hover:border-accent/40 rounded-xl p-5 flex flex-col justify-between transition-all duration-200 shadow-sm hover:shadow-md group"
                >
                  <div>
                    {/* Top Row: Icon + Permission */}
                    <div className="flex items-center justify-between mb-3">
                      <div className="w-9 h-9 rounded-lg bg-[#141415] border border-white/[0.08] flex items-center justify-center text-accent group-hover:text-[#F4F2ED] group-hover:border-accent/40 transition-colors">
                        <IconComp className="w-4 h-4" />
                      </div>
                      {getPermissionBadge(tool.permission)}
                    </div>

                    {/* Tool Name & Description */}
                    <h3 className="text-sm font-semibold font-mono text-[#F4F2ED] tracking-wide mb-1">
                      {tool.name}
                    </h3>
                    <p className="text-xs text-[#A0A0A0] line-clamp-3 leading-relaxed mb-4">
                      {tool.description}
                    </p>
                  </div>

                  {/* Schema Preview & Test Action */}
                  <div className="border-t border-white/[0.05] pt-3.5 flex items-center justify-between">
                    <span className="text-[11px] font-mono text-[#767676]">
                      {Object.keys(tool.input_schema?.properties || {}).length} parameter(s)
                    </span>
                    <button
                      onClick={() => openTester(tool)}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium text-accent bg-[#141415] hover:bg-accent/20 hover:text-[#F4F2ED] border border-white/[0.08] hover:border-accent/40 flex items-center gap-1.5 transition-all"
                    >
                      <Play className="w-3 h-3 text-accent" />
                      Test Console
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Interactive Tool Playground / Tester Modal */}
      {activeTesterTool && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#16171B] border border-[#2F3038] rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in duration-150">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-[#26272E] bg-[#1A1B20] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-[#24262E] border border-[#333540] flex items-center justify-center text-[#C5A880]">
                  <Terminal className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-[#F3EFE0] font-mono">
                    {activeTesterTool.name}
                  </h3>
                  <p className="text-xs text-[#9E9A90]">Interactive Execution & Sandbox Tester</p>
                </div>
              </div>
              <button
                onClick={() => setActiveTesterTool(null)}
                className="text-[#9E9A90] hover:text-[#F3EFE0] p-1.5 rounded-lg hover:bg-[#24262E] transition-colors"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto flex-1 space-y-5">
              {/* Tool Schema & Info */}
              <div className="bg-[#121316] border border-[#23242B] rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-[#C5A880]">
                    Description & Parameters
                  </span>
                  {getPermissionBadge(activeTesterTool.permission)}
                </div>
                <p className="text-xs text-[#B5B2A8] leading-relaxed mb-3">
                  {activeTesterTool.description}
                </p>
                <div className="bg-[#0C0D0F] p-2.5 rounded-lg border border-[#1E1F24] font-mono text-[11px] text-[#A8A49A] overflow-x-auto">
                  {JSON.stringify(activeTesterTool.input_schema, null, 2)}
                </div>
              </div>

              {/* JSON Parameters Input */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-medium text-[#E5D4B3] flex items-center gap-1.5">
                    <Terminal className="w-3.5 h-3.5 text-[#C5A880]" />
                    Input Parameters (JSON)
                  </label>
                  <button
                    onClick={() => {
                      const sample = SAMPLE_INPUTS[activeTesterTool.name] || {};
                      setTesterParams(JSON.stringify(sample, null, 2));
                    }}
                    className="text-[11px] text-[#C5A880] hover:underline"
                  >
                    Reset to Sample Input
                  </button>
                </div>
                <textarea
                  rows={4}
                  value={testerParams}
                  onChange={(e) => setTesterParams(e.target.value)}
                  className="w-full bg-[#0E0F12] border border-[#282A33] rounded-lg p-3 font-mono text-xs text-[#F3EFE0] focus:outline-none focus:border-[#C5A880]/60 transition-colors"
                />
              </div>

              {/* Execution Result Box */}
              {executionResult && (
                <div className="border border-[#2A2B33] rounded-xl bg-[#111215] p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {executionResult.success ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <XCircle className="w-4 h-4 text-rose-400" />
                      )}
                      <span className="text-xs font-semibold font-mono text-[#F3EFE0]">
                        {executionResult.success ? 'Execution Succeeded' : 'Execution Failed'}
                      </span>
                    </div>
                    {executionResult.source && (
                      <span className="text-[11px] font-mono text-[#73716B]">
                        Source: {executionResult.source}
                      </span>
                    )}
                  </div>

                  {executionResult.error && (
                    <div className="text-xs text-rose-300 bg-rose-950/40 border border-rose-900/50 p-2.5 rounded-lg mb-2">
                      {executionResult.error}
                    </div>
                  )}

                  {executionResult.data && (
                    <div className="bg-[#090A0C] border border-[#1E1F24] p-3 rounded-lg overflow-x-auto max-h-60">
                      <pre className="text-xs font-mono text-[#A8C7FA] whitespace-pre-wrap">
                        {JSON.stringify(executionResult.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3.5 border-t border-[#26272E] bg-[#1A1B20] flex items-center justify-between">
              <span className="text-xs text-[#73716B]">
                Executes via isolated backend executor with 10s timeout & SSRF guard
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setActiveTesterTool(null)}
                  className="px-4 py-2 rounded-lg text-xs font-medium text-[#9E9A90] hover:text-[#F3EFE0] hover:bg-[#23242A] transition-colors"
                >
                  Close
                </button>
                <button
                  onClick={runTesterExecution}
                  disabled={executeMutation.isPending}
                  className="px-4 py-2 rounded-lg text-xs font-semibold text-[#121316] bg-gradient-to-r from-[#E5D4B3] to-[#C5A880] hover:brightness-110 flex items-center gap-2 transition-all shadow-md disabled:opacity-50"
                >
                  {executeMutation.isPending ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Play className="w-3.5 h-3.5 fill-current" />
                  )}
                  {executeMutation.isPending ? 'Executing...' : 'Run Tool'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
