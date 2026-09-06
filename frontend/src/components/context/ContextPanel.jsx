import React, { useState } from 'react';
import { useAppStore } from '../../stores/useAppStore';
import { useAuthStore } from '../../stores/useAuthStore';
import { X, Search, FileText, Wrench, Info, Loader2, Sparkles } from 'lucide-react';
import { retrievalApi } from '../../api/retrievalApi';

const DEV_USER_ID = '00000000-0000-0000-0000-000000000001';

export default function ContextPanel() {
  const toggleContextPanel = useAppStore((state) => state.toggleContextPanel);
  const user = useAuthStore((state) => state.user);
  const effectiveUserId = user?.id || DEV_USER_ID;

  const [searchQuery, setSearchQuery] = useState('');
  const [searchMode, setSearchMode] = useState('hybrid'); // hybrid, vector, keyword
  const [isSearching, setIsSearching] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [searchError, setSearchError] = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    setSearchError(null);

    try {
      let res;
      const payload = {
        query: searchQuery.trim(),
        user_id: effectiveUserId,
        top_k: 3,
      };

      if (searchMode === 'vector') {
        res = await retrievalApi.vectorSearch(payload);
      } else if (searchMode === 'keyword') {
        res = await retrievalApi.keywordSearch(payload);
      } else {
        res = await retrievalApi.hybridSearch(payload);
      }

      setSearchResults(res.results || []);
    } catch (err) {
      console.error('[ContextPanel] Retrieval failed:', err);
      setSearchError(err.message || 'Search failed');
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <aside className="w-80 h-full border-l border-border bg-surface2 flex flex-col flex-shrink-0 transition-all duration-300">
      <div className="flex items-center justify-between p-4 border-b border-border">
        <h2 className="text-sm font-semibold tracking-wide">Context & Retrieval</h2>
        <button
          onClick={toggleContextPanel}
          className="p-1 hover:bg-muted rounded-md text-muted-foreground hover:text-gray-200 transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Knowledge Retrieval Tool */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-300">
            <Sparkles size={16} className="text-accent" />
            <span>Semantic Knowledge Search</span>
          </div>

          <form onSubmit={handleSearch} className="space-y-2">
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Query ingested documents..."
                className="w-full bg-background border border-border rounded-md px-3 py-1.5 text-xs text-gray-200 placeholder:text-muted-foreground outline-none focus:border-accent"
              />
              <button
                type="submit"
                disabled={isSearching || !searchQuery.trim()}
                className="absolute right-1.5 top-1.5 text-muted-foreground hover:text-accent disabled:opacity-40"
              >
                {isSearching ? <Loader2 size={13} className="animate-spin text-accent" /> : <Search size={13} />}
              </button>
            </div>

            <div className="flex items-center justify-between text-[10px] text-muted-foreground px-1">
              <span>Mode:</span>
              <div className="flex gap-2">
                {['hybrid', 'vector', 'keyword'].map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setSearchMode(m)}
                    className={`capitalize px-1.5 py-0.5 rounded transition-colors ${
                      searchMode === m
                        ? 'bg-accent/20 text-accent border border-accent/30'
                        : 'hover:text-gray-300'
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>
          </form>

          {searchError && (
            <div className="text-[11px] text-red-400 bg-red-400/10 border border-red-400/20 rounded p-2">
              {searchError}
            </div>
          )}

          {searchResults.length > 0 && (
            <div className="space-y-2">
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                Top Matches ({searchResults.length})
              </span>
              {searchResults.map((res, i) => (
                <div
                  key={res.chunk_id || i}
                  className="bg-background rounded-md p-2.5 text-xs border border-border space-y-1"
                >
                  <div className="flex items-center justify-between text-[10px] text-accent">
                    <span className="truncate max-w-[140px]" title={res.metadata?.filename}>
                      {res.metadata?.filename || 'Document'}
                    </span>
                    <span>Score: {Math.round(res.similarity_score * 100)}%</span>
                  </div>
                  <p className="text-[11px] text-gray-300 line-clamp-3 leading-relaxed">
                    {res.content}
                  </p>
                  <div className="text-[9px] text-muted-foreground">
                    Page {res.page_number} · Chunk {res.chunk_index}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Thread Info + RAG Status */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-300">
            <Info size={16} className="text-accent" />
            <span>Thread Info</span>
          </div>
          <div className="bg-background rounded-md p-3 text-xs text-muted-foreground space-y-2 border border-border">
            <div className="flex justify-between">
              <span>Status</span>
              <span className="text-gray-300">Active</span>
            </div>
            <div className="flex justify-between">
              <span>Embeddings</span>
              <span className="text-accent">BGE-M3 (1024-d)</span>
            </div>
            <div className="flex justify-between">
              <span>Reranker</span>
              <span className="text-accent">BGE-v2-m3</span>
            </div>
          </div>
        </div>

        {/* Sources */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-300">
            <FileText size={16} className="text-accent" />
            <span>Active Sources</span>
          </div>
          <div className="text-xs text-muted-foreground italic">
            {searchResults.length > 0 ? `${searchResults.length} chunks referenced` : 'No active citations yet.'}
          </div>
        </div>

        {/* Tools */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-300">
            <Wrench size={16} className="text-accent" />
            <span>Tools</span>
          </div>
          <div className="text-xs text-muted-foreground italic">No tools used.</div>
        </div>
      </div>
    </aside>
  );
}
