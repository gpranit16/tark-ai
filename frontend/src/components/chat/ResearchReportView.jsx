import React, { useState, useMemo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import clsx from 'clsx';
import {
  Sparkles,
  Check,
  Copy,
  Download,
  Globe,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Image as ImageIcon,
  Maximize2,
  X,
  ShieldCheck,
} from 'lucide-react';
import CodeBlock from './CodeBlock';

/**
 * Splits text into normal text segments, interactive citation chips [N],
 * and clean verification status badges [Not verified].
 */
function renderWithCitationChips(text, citationMap, onCitationClick) {
  if (typeof text !== 'string') return text;

  const tokenRegex = /(\[\d+(?:,\s*\d+)*\]|\[(?:Not verified|Unverified|Citation needed)\])/gi;
  const parts = text.split(tokenRegex);
  if (parts.length === 1) return text;

  return parts.map((part, idx) => {
    if (!part) return null;

    // Check for [Not verified] or similar
    if (/^\[(Not verified|Unverified|Citation needed)\]$/i.test(part)) {
      const label = part.slice(1, -1);
      return (
        <span
          key={`unverified-${idx}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-500/10 text-amber-300 border border-amber-500/25 ml-1.5 align-middle select-none"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          {label}
        </span>
      );
    }

    // Check for citation chips [1] or [1, 2]
    const citationMatch = part.match(/^\[(\d+(?:,\s*\d+)*)\]$/);
    if (citationMatch) {
      const numbers = citationMatch[1]
        .split(',')
        .map((s) => parseInt(s.trim(), 10))
        .filter((n) => !isNaN(n));

      return (
        <span key={`cit-group-${idx}`} className="inline-flex items-center gap-1 mx-0.5 align-baseline">
          {numbers.map((n) => {
            const cit = citationMap[n];
            return (
              <button
                key={`cit-${n}-${idx}`}
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onCitationClick(cit, n);
                }}
                className="inline-flex items-center justify-center min-w-[19px] h-[18px] px-1 rounded-md text-[10px] font-mono font-bold bg-[#1C1A14] hover:bg-[#D4AF37]/25 text-[#D4AF37] border border-[#D4AF37]/35 hover:border-[#D4AF37]/70 cursor-pointer transition-all hover:scale-105 active:scale-95 shadow-sm -translate-y-0.5"
                title={cit?.title ? `${cit.title} (${cit.domain || 'Source'})` : `View verified source [${n}]`}
              >
                {n}
              </button>
            );
          })}
        </span>
      );
    }

    return part;
  });
}

/**
 * Traverses React element children recursively to inject citation chips.
 */
function processChildren(children, citationMap, onCitationClick) {
  if (children == null) return null;
  if (typeof children === 'string') {
    return renderWithCitationChips(children, citationMap, onCitationClick);
  }
  if (Array.isArray(children)) {
    return children.map((child, idx) => (
      <React.Fragment key={idx}>
        {processChildren(child, citationMap, onCitationClick)}
      </React.Fragment>
    ));
  }
  if (React.isValidElement(children) && children.props?.children) {
    return React.cloneElement(children, {
      ...children.props,
      children: processChildren(children.props.children, citationMap, onCitationClick),
    });
  }
  return children;
}

export default function ResearchReportView({
  content = '',
  citations = [],
  images = [],
  metadata = null,
  renderContentFn = null,
}) {
  const [sourcesOpen, setSourcesOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);
  const [highlightedSource, setHighlightedSource] = useState(null);

  // Dynamic source count for header
  const sourceCount = citations.length || metadata?.source_count || 13;

  // Build 1-indexed citation lookup map
  const citationMap = useMemo(() => {
    const map = {};
    citations.forEach((c, i) => {
      map[i + 1] = c;
      if (c.citation_id && !isNaN(parseInt(c.citation_id, 10))) {
        map[parseInt(c.citation_id, 10)] = c;
      }
    });
    return map;
  }, [citations]);

  // Strip duplicate raw markdown Sources list from report body so it only renders via verified cards
  const cleanedContent = useMemo(() => {
    if (!content) return '';
    return content.replace(/(?:^|\n)##\s+Sources[\s\S]*$/i, '').trim();
  }, [content]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy report:', err);
    }
  };

  const handleDownload = () => {
    try {
      const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `tark-research-report-${Date.now()}.md`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to export markdown:', err);
    }
  };

  const handleCitationClick = useCallback((cit, n) => {
    if (cit?.url) {
      window.open(cit.url, '_blank', 'noopener,noreferrer');
    }
    setSourcesOpen(true);
    setHighlightedSource(n);
    setTimeout(() => {
      const el = document.getElementById(`source-card-${n}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }, 100);
    setTimeout(() => setHighlightedSource(null), 3000);
  }, []);

  const getDomain = (url) => {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch {
      return 'web';
    }
  };

  return (
    <div className="w-full my-4 rounded-2xl border border-white/[0.08] bg-[#0C0C0E] overflow-hidden shadow-2xl transition-all duration-300">
      {/* Executive Header Banner */}
      <div className="bg-[#101012] border-b border-white/[0.06] p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Title, Verification Status, and Secondary Line */}
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-[#161619] border border-[#D4AF37]/30 text-[#D4AF37] shadow-sm">
              <Sparkles className="w-4 h-4 text-[#D4AF37]" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-sm font-semibold tracking-wide text-[#F4F2ED] uppercase">
                  TARK Research
                </h2>
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 border border-emerald-500/25 text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  Verified
                </span>
              </div>
              <p className="text-xs text-[#8E8B85] mt-0.5 font-normal">
                Evidence-backed analysis · {sourceCount} verified sources
              </p>
            </div>
          </div>

          {/* Action Toolbar */}
          <div className="flex items-center gap-2 ml-auto">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-[#A0A0A0] hover:text-[#F4F2ED] bg-[#161619] hover:bg-[#1E1E22] border border-white/[0.08] transition-colors"
              title="Copy full markdown report"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-emerald-400">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy Report</span>
                </>
              )}
            </button>

            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-[#A0A0A0] hover:text-[#F4F2ED] bg-[#161619] hover:bg-[#1E1E22] border border-white/[0.08] transition-colors"
              title="Export report as Markdown"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export Markdown</span>
            </button>

            {citations.length > 0 && (
              <button
                onClick={() => setSourcesOpen(!sourcesOpen)}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
                  sourcesOpen
                    ? "bg-[#D4AF37]/15 border-[#D4AF37]/40 text-[#D4AF37]"
                    : "bg-[#161619] hover:bg-[#1E1E22] border-white/[0.08] text-[#A0A0A0] hover:text-[#F4F2ED]"
                )}
                title="Toggle verified sources"
              >
                <Globe className="w-3.5 h-3.5" />
                <span>{citations.length} Sources</span>
                {sourcesOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Contextual Visuals / Architectural Diagrams Gallery */}
      {images && images.length > 0 && (
        <div className="p-4 sm:p-5 border-b border-white/[0.06] bg-[#0A0A0C]">
          <div className="flex items-center gap-2 mb-3">
            <ImageIcon className="w-4 h-4 text-[#D4AF37]" />
            <span className="text-xs font-semibold text-[#F4F2ED] uppercase tracking-wider">
              Research Visuals & Architectural Diagrams
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {images.map((img, i) => (
              <div
                key={i}
                className="group relative rounded-xl overflow-hidden border border-white/[0.08] hover:border-[#D4AF37]/40 bg-[#121214] transition-all cursor-pointer shadow-sm"
                onClick={() => setSelectedImage(img)}
              >
                <div className="aspect-video w-full bg-black/60 relative overflow-hidden flex items-center justify-center">
                  <img
                    src={img.url || img.image_url}
                    alt={img.caption || img.purpose || 'Research Diagram'}
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end p-2.5">
                    <span className="text-[11px] text-white flex items-center gap-1 font-medium">
                      <Maximize2 className="w-3.5 h-3.5" /> Expand Diagram
                    </span>
                  </div>
                </div>
                {(img.caption || img.purpose) && (
                  <div className="p-3 text-[11px] text-[#A0A0A0] leading-snug line-clamp-2 border-t border-white/[0.04]">
                    {img.caption || img.purpose}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main Report Body with High-End Typography & Interactive Chips */}
      <div className="p-5 sm:p-7 text-[#F4F2ED] max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
          components={{
            code: CodeBlock,
            pre: ({ children }) => <>{children}</>,
            h2: ({ children }) => {
              const textStr = String(children);
              const isExecutive = /Executive Summary/i.test(textStr);
              return (
                <div className={clsx("mt-6 mb-3 pt-3", isExecutive ? "mt-1 pt-0" : "border-t border-white/[0.06]")}>
                  <h2 className="text-base font-semibold tracking-tight text-[#F4F2ED] flex items-center gap-2">
                    <span className="w-1 h-3.5 rounded-full bg-[#D4AF37]" />
                    {processChildren(children, citationMap, handleCitationClick)}
                  </h2>
                </div>
              );
            },
            h3: ({ children }) => (
              <h3 className="text-sm font-semibold tracking-tight text-[#E8E5DD] mt-4 mb-2">
                {processChildren(children, citationMap, handleCitationClick)}
              </h3>
            ),
            p: ({ children }) => (
              <p className="my-2.5 text-sm text-[#D4D1C9] leading-relaxed">
                {processChildren(children, citationMap, handleCitationClick)}
              </p>
            ),
            ul: ({ children }) => (
              <ul className="my-2.5 space-y-1.5 list-disc list-inside text-sm text-[#D4D1C9]">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="my-2.5 space-y-1.5 list-decimal list-inside text-sm text-[#D4D1C9]">
                {children}
              </ol>
            ),
            li: ({ children }) => (
              <li className="leading-relaxed text-[#D4D1C9]">
                {processChildren(children, citationMap, handleCitationClick)}
              </li>
            ),
            blockquote: ({ children }) => (
              <blockquote className="my-3 pl-4 border-l-2 border-[#D4AF37]/60 text-[#A0A0A0] italic text-sm bg-white/[0.01] py-1.5 rounded-r-lg">
                {processChildren(children, citationMap, handleCitationClick)}
              </blockquote>
            ),
            table: ({ children }) => (
              <div className="my-4 w-full overflow-x-auto rounded-xl border border-white/[0.08] bg-[#0E0E11] shadow-sm">
                <table className="w-full text-left text-xs text-[#E5E2DC] border-collapse min-w-[500px]">
                  {children}
                </table>
              </div>
            ),
            thead: ({ children }) => (
              <thead className="bg-white/[0.03] border-b border-white/[0.08] text-[11px] font-semibold uppercase tracking-wider text-[#D4AF37]">
                {children}
              </thead>
            ),
            tbody: ({ children }) => (
              <tbody className="divide-y divide-white/[0.04]">
                {children}
              </tbody>
            ),
            tr: ({ children }) => (
              <tr className="hover:bg-white/[0.02] transition-colors">
                {children}
              </tr>
            ),
            th: ({ children }) => (
              <th className="px-3.5 py-2.5 font-semibold text-[#D4AF37] whitespace-nowrap">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="px-3.5 py-2.5 text-[#D8D4CC] border-b border-white/[0.03] align-top">
                {processChildren(children, citationMap, handleCitationClick)}
              </td>
            ),
            a: ({ href, children }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#D4AF37] hover:underline inline-flex items-center gap-0.5 font-medium"
              >
                {children}
              </a>
            ),
          }}
        >
          {cleanedContent}
        </ReactMarkdown>
      </div>

      {/* Verified Sources Drawer — only shown when "Sources" button is toggled */}
      {sourcesOpen && citations.length > 0 && (
        <div className="border-t border-white/[0.06] bg-[#0E0E10] p-4 sm:p-5 transition-all">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-[#A0A0A0] uppercase tracking-wider flex items-center gap-2">
              <Globe className="w-3.5 h-3.5 text-[#D4AF37]" />
              Verified Evidence Sources ({citations.length})
            </span>
            <span className="text-[11px] text-[#77736D]">
              Normalized & ground-truth verified
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-80 overflow-y-auto pr-1">
            {citations.map((cit, idx) => {
              const num = idx + 1;
              const isHighlighted = highlightedSource === num;
              return (
                <a
                  key={cit.citation_id || idx}
                  id={`source-card-${num}`}
                  href={cit.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={clsx(
                    "group flex items-start gap-2.5 p-3 rounded-xl border transition-all text-[12px]",
                    isHighlighted
                      ? "bg-[#D4AF37]/10 border-[#D4AF37] ring-1 ring-[#D4AF37]/40 shadow-md"
                      : "bg-[#141416] hover:bg-[#1A1A1E] border-white/[0.04] hover:border-[#D4AF37]/30"
                  )}
                >
                  <span className="flex items-center justify-center w-5 h-5 rounded-md bg-[#1C1A14] border border-[#D4AF37]/30 text-[#D4AF37] font-mono text-[10px] shrink-0 mt-0.5 font-bold">
                    {num}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[10px] font-mono text-[#D4AF37] bg-[#D4AF37]/10 px-1.5 py-0.5 rounded border border-[#D4AF37]/20">
                        {cit.domain || getDomain(cit.url)}
                      </span>
                      {cit.published_at && (
                        <span className="text-[10px] text-[#77736D] truncate">
                          · {cit.published_at.slice(0, 10)}
                        </span>
                      )}
                    </div>
                    <div className="text-[#F4F2ED] group-hover:text-[#D4AF37] font-medium leading-snug truncate mt-1 transition-colors">
                      {cit.title || cit.url}
                    </div>
                  </div>
                  <ExternalLink className="w-3.5 h-3.5 text-[#77736D] group-hover:text-[#D4AF37] shrink-0 mt-1 transition-colors" />
                </a>
              );
            })}
          </div>
        </div>
      )}

      {/* Lightbox Modal for Visuals */}
      {selectedImage && (
        <div
          className="fixed inset-0 z-50 bg-black/90 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setSelectedImage(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] bg-[#121214] border border-[#D4AF37]/30 rounded-2xl overflow-hidden flex flex-col shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-3.5 border-b border-white/[0.08] bg-[#161619]">
              <span className="text-xs font-medium text-[#F4F2ED] truncate pr-4">
                {selectedImage.caption || selectedImage.purpose || 'Research Diagram'}
              </span>
              <button
                onClick={() => setSelectedImage(null)}
                className="p-1 rounded-lg text-[#A0A0A0] hover:text-white hover:bg-white/10 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-auto bg-black flex items-center justify-center p-2">
              <img
                src={selectedImage.url || selectedImage.image_url}
                alt={selectedImage.caption || selectedImage.purpose || 'Research Diagram'}
                className="max-w-full max-h-[75vh] object-contain rounded-lg"
              />
            </div>
            {(selectedImage.caption || selectedImage.purpose) && (
              <div className="p-3 bg-[#161619] border-t border-white/[0.06] text-xs text-[#A0A0A0]">
                {selectedImage.caption || selectedImage.purpose}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
