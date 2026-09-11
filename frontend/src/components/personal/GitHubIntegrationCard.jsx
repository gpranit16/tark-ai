import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle2,
  ExternalLink,
  Loader2,
  Unlink,
  Key,
  Shield,
  GitBranch,
  GitPullRequest,
  AlertCircle,
  FolderGit2,
  Terminal,
  FileCode,
  X,
  Lock,
} from 'lucide-react';
import clsx from 'clsx';
import { integrationsApi } from '../../api/integrationsApi';

function GitHubIcon({ size = 20, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
      />
    </svg>
  );
}

export default function GitHubIntegrationCard() {
  const queryClient = useQueryClient();
  const [isTokenModalOpen, setIsTokenModalOpen] = useState(false);
  const [tokenInput, setTokenInput] = useState('');
  const [actionError, setActionError] = useState(null);

  // Status Query
  const { data: status, isLoading: isStatusLoading } = useQuery({
    queryKey: ['integration-github-status'],
    queryFn: () => integrationsApi.getGitHubStatus(),
  });

  const isConnected = !!(status?.connected || status?.is_connected);

  // Save Token Mutation
  const saveTokenMutation = useMutation({
    mutationFn: (token) => integrationsApi.saveGitHubToken(token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integration-github-status'] });
      setIsTokenModalOpen(false);
      setTokenInput('');
      setActionError(null);
    },
    onError: (err) => {
      setActionError(err.message || 'Failed to save GitHub Personal Access Token.');
    },
  });

  // Disconnect Mutation
  const disconnectMutation = useMutation({
    mutationFn: () => integrationsApi.disconnectGitHub(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integration-github-status'] });
      setActionError(null);
    },
    onError: (err) => {
      setActionError(err.message || 'Failed to disconnect GitHub.');
    },
  });

  const handleSaveTokenSubmit = (e) => {
    e.preventDefault();
    if (!tokenInput.trim()) return;
    saveTokenMutation.mutate(tokenInput.trim());
  };

  const handleDisconnect = () => {
    if (window.confirm('Disconnect your personal GitHub integration?')) {
      disconnectMutation.mutate();
    }
  };

  if (isStatusLoading) {
    return (
      <div className="bg-[#101012] border border-white/[0.06] rounded-2xl p-6 flex items-center justify-center min-h-[160px]">
        <Loader2 className="animate-spin text-accent" size={20} />
      </div>
    );
  }

  return (
    <div className="bg-[#101012] border border-white/[0.06] hover:border-white/[0.12] rounded-2xl p-6 transition-all duration-200">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap sm:flex-nowrap">
        <div className="flex items-center gap-3.5 min-w-0">
          <div className="w-12 h-12 rounded-xl bg-[#18181C] border border-white/[0.08] flex items-center justify-center shadow-inner shrink-0">
            <GitHubIcon className="text-white" size={22} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-[15px] font-medium text-[#F2F0EB]">GitHub MCP Integration</h3>
              {isConnected ? (
                <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                  <CheckCircle2 size={11} />
                  Connected
                </span>
              ) : (
                <span className="text-[11px] font-medium text-[#85817B] bg-white/[0.04] border border-white/[0.08] px-2 py-0.5 rounded-full">
                  Disconnected
                </span>
              )}
            </div>
            <p className="text-[12.5px] text-[#85817B] mt-0.5 leading-relaxed">
              Model Context Protocol (MCP) toolchain for repositories, code files, issues, pull requests, commits, branches, and GitHub Actions.
            </p>
          </div>
        </div>

        {/* Action Button */}
        <div className="shrink-0 flex items-center gap-2">
          {isConnected ? (
            <>
              <button
                onClick={() => setIsTokenModalOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[12px] font-medium text-[#EDE8DF] hover:text-accent bg-[#18181C] hover:bg-[#202026] border border-white/[0.08] transition-all cursor-pointer"
              >
                <Key size={12} />
                <span>Update PAT</span>
              </button>
              {status?.token_source === 'user' && (
                <button
                  onClick={handleDisconnect}
                  disabled={disconnectMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[12px] font-medium text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/15 border border-red-500/20 transition-all cursor-pointer disabled:opacity-50"
                >
                  {disconnectMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Unlink size={12} />}
                  <span>Disconnect</span>
                </button>
              )}
            </>
          ) : (
            <button
              onClick={() => setIsTokenModalOpen(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-[12.5px] font-medium bg-accent text-[#080808] hover:bg-accent-highlight active:scale-95 transition-all shadow-[0_2px_14px_rgba(201,168,106,0.25)] cursor-pointer"
            >
              <Key size={13} />
              <span>Connect GitHub PAT</span>
            </button>
          )}
        </div>
      </div>

      {actionError && (
        <div className="mt-4 flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-[12px] text-red-400">
          <AlertCircle size={14} className="shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Connected Details & Capabilities Preview */}
      {isConnected && (
        <div className="mt-5 pt-5 border-t border-white/[0.04] space-y-4">
          <div className="flex flex-wrap items-center gap-4 text-[12px] text-[#A3A09A]">
            {status?.account_login && (
              <div className="flex items-center gap-1.5 bg-[#141418] px-3 py-1.5 rounded-xl border border-white/[0.06]">
                {status?.avatar_url ? (
                  <img src={status.avatar_url} alt="" className="w-4 h-4 rounded-full" />
                ) : (
                  <GitHubIcon size={13} className="text-accent" />
                )}
                <span className="text-[#EDE8DF] font-medium">@{status.account_login}</span>
                {status.account_name && status.account_name !== status.account_login && (
                  <span className="text-[#77736D]">({status.account_name})</span>
                )}
              </div>
            )}

            <div className="flex items-center gap-1.5 bg-[#141418] px-3 py-1.5 rounded-xl border border-white/[0.06]">
              <Lock size={12} className="text-emerald-400" />
              <span>Source:</span>
              <span className="text-[#EDE8DF] font-medium font-mono text-[11px]">
                {status?.token_source === 'env' ? 'Server (.env PAT)' : 'Personal Token (Encrypted)'}
              </span>
            </div>

            <div className="flex items-center gap-1.5 bg-[#141418] px-3 py-1.5 rounded-xl border border-white/[0.06]">
              <Terminal size={12} className="text-accent" />
              <span>Active Tools:</span>
              <span className="text-accent font-semibold font-mono text-[11px]">21 MCP Tools</span>
            </div>
          </div>

          {/* Capabilities Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1">
            <div className="p-2.5 rounded-xl bg-[#141418] border border-white/[0.05] text-[11.5px] space-y-1">
              <div className="flex items-center gap-1.5 text-[#EDE8DF] font-medium">
                <FolderGit2 size={13} className="text-accent" />
                <span>Repositories</span>
              </div>
              <p className="text-[10.5px] text-[#77736D]">Search, inspect, and list repos</p>
            </div>

            <div className="p-2.5 rounded-xl bg-[#141418] border border-white/[0.05] text-[11.5px] space-y-1">
              <div className="flex items-center gap-1.5 text-[#EDE8DF] font-medium">
                <FileCode size={13} className="text-blue-400" />
                <span>Files & Code</span>
              </div>
              <p className="text-[10.5px] text-[#77736D]">Read, write, commit & delete</p>
            </div>

            <div className="p-2.5 rounded-xl bg-[#141418] border border-white/[0.05] text-[11.5px] space-y-1">
              <div className="flex items-center gap-1.5 text-[#EDE8DF] font-medium">
                <GitPullRequest size={13} className="text-purple-400" />
                <span>Issues & PRs</span>
              </div>
              <p className="text-[10.5px] text-[#77736D]">List, create, comment & merge</p>
            </div>

            <div className="p-2.5 rounded-xl bg-[#141418] border border-white/[0.05] text-[11.5px] space-y-1">
              <div className="flex items-center gap-1.5 text-[#EDE8DF] font-medium">
                <GitBranch size={13} className="text-emerald-400" />
                <span>Actions & Branch</span>
              </div>
              <p className="text-[10.5px] text-[#77736D]">Workflows, dispatch, branches</p>
            </div>
          </div>

          {/* Safety Notice */}
          <div className="flex items-start gap-2 p-3 rounded-xl bg-amber-500/5 border border-amber-500/15 text-[11.5px] text-amber-300/90 leading-relaxed">
            <Shield size={14} className="shrink-0 mt-0.5 text-amber-400" />
            <span>
              <strong>Write Confirmation Guard Active:</strong> Any write or destructive operation (creating commits, deleting files, creating PRs/issues, triggering Actions) requires your explicit in-chat approval before execution.
            </span>
          </div>
        </div>
      )}

      {/* Token Modal */}
      {isTokenModalOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#121216] border border-white/[0.1] rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-2 text-sm font-semibold text-[#F2F0EB]">
                <GitHubIcon size={16} className="text-accent" />
                <span>Configure GitHub Personal Access Token</span>
              </div>
              <button
                onClick={() => setIsTokenModalOpen(false)}
                className="text-[#77736D] hover:text-[#EDE8DF] transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleSaveTokenSubmit} className="space-y-4">
              <p className="text-xs text-[#8E8B85] leading-relaxed">
                Provide a GitHub Personal Access Token (classic or fine-grained) with <code className="text-accent bg-white/[0.05] px-1 py-0.5 rounded">repo</code> and <code className="text-accent bg-white/[0.05] px-1 py-0.5 rounded">workflow</code> scopes. Tokens are encrypted server-side with AES-128-CBC and never exposed in responses or logs.
              </p>

              <div>
                <label className="text-xs font-medium text-[#EDE8DF] block mb-1.5">
                  GitHub Personal Access Token (ghp_...)
                </label>
                <input
                  type="password"
                  required
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                  className="w-full bg-[#18181E] border border-white/[0.08] focus:border-accent/60 rounded-xl px-3.5 py-2.5 text-xs text-[#EDE8DF] placeholder-[#666672] outline-none font-mono"
                  autoFocus
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsTokenModalOpen(false)}
                  className="px-3.5 py-2 rounded-xl text-xs font-medium text-[#8E8B85] hover:text-[#EDE8DF] transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saveTokenMutation.isPending || !tokenInput.trim()}
                  className="px-4 py-2 bg-accent text-black font-semibold rounded-xl text-xs hover:bg-accent-highlight transition-all disabled:opacity-50 flex items-center gap-1.5 shadow-[0_0_15px_rgba(201,168,106,0.2)] cursor-pointer"
                >
                  {saveTokenMutation.isPending ? (
                    <>
                      <Loader2 size={13} className="animate-spin" />
                      <span>Validating...</span>
                    </>
                  ) : (
                    <span>Save & Validate Token</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
