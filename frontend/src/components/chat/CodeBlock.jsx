import { useState } from 'react';
import { Check, Copy, ChevronDown, ChevronUp, FileCode, GitCommit } from 'lucide-react';
import clsx from 'clsx';

/**
 * Recursively extract plain string content from React children (strings, arrays, or VDOM elements).
 */
function extractTextFromChildren(children) {
  if (typeof children === 'string') return children;
  if (typeof children === 'number') return String(children);
  if (!children) return '';
  if (Array.isArray(children)) {
    return children.map(extractTextFromChildren).join('');
  }
  if (typeof children === 'object' && children.props && children.props.children !== undefined) {
    return extractTextFromChildren(children.props.children);
  }
  return '';
}

export default function CodeBlock({ inline, className, children, node, ...props }) {
  const [copied, setCopied] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);

  const rawCode = extractTextFromChildren(children).replace(/\n$/, '');
  const match = /language-(\w+)(?::([^\s]+))?/.exec(className || '');
  
  const hasLanguage = Boolean(match);
  const language = match ? match[1] : 'text';
  let filePath = match && match[2] ? match[2] : null;

  // Determine if code block is inline
  const isInline = inline || (!hasLanguage && !rawCode.includes('\n'));

  // If inline code snippet, render inline badge
  if (isInline) {
    return (
      <code className="bg-[#242427] text-[#D4AF37] px-1.5 py-0.5 rounded text-[13px] font-mono border border-border/40" {...props}>
        {children}
      </code>
    );
  }

  // If filename wasn't in class but in first line comment (e.g., # filename: app.py or // filename: app.jsx)
  if (!filePath) {
    const firstLine = rawCode.split('\n')[0] || '';
    const fileCommentMatch = /(?:#|\/\/|\/\*)\s*(?:file|filename|path):\s*([^\s\*]+)/i.exec(firstLine);
    if (fileCommentMatch) {
      filePath = fileCommentMatch[1];
    }
  }

  const isDiff = language === 'diff';
  const lines = rawCode.split('\n');
  const isLong = lines.length > 25;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(rawCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
    }
  };

  const renderDiffLines = () => {
    return lines.map((line, idx) => {
      let lineStyle = 'text-gray-300';
      let bgStyle = '';

      if (line.startsWith('+') && !line.startsWith('+++')) {
        lineStyle = 'text-emerald-300 font-medium';
        bgStyle = 'bg-emerald-950/30 -mx-4 px-4';
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        lineStyle = 'text-rose-300 line-through opacity-80';
        bgStyle = 'bg-rose-950/30 -mx-4 px-4';
      } else if (line.startsWith('@@')) {
        lineStyle = 'text-sky-300/80 italic font-mono';
        bgStyle = 'bg-sky-950/20 -mx-4 px-4';
      }

      return (
        <div key={idx} className={clsx('flex items-start text-xs font-mono leading-relaxed', bgStyle)}>
          <span className="w-6 text-muted-foreground/40 select-none text-[11px] shrink-0 text-right pr-2">
            {idx + 1}
          </span>
          <span className={clsx('flex-1 whitespace-pre', lineStyle)}>
            {line}
          </span>
        </div>
      );
    });
  };

  return (
    <div className="not-prose my-3 rounded-lg border border-border/80 bg-[#141416] overflow-hidden shadow-sm">
      {/* Code Header Bar */}
      <div className="flex items-center justify-between px-3.5 py-1.5 bg-[#1c1c1f] border-b border-border/60 text-xs select-none">
        <div className="flex items-center gap-2 truncate">
          {isDiff ? (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/15 text-[#D4AF37] font-mono text-[11px] font-semibold border border-amber-500/30">
              <GitCommit size={11} /> DIFF
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-surface2 text-gray-300 font-mono text-[11px] uppercase border border-border/40">
              <FileCode size={11} className="text-[#D4AF37]" /> {language}
            </span>
          )}

          {filePath && (
            <span className="text-gray-300 font-mono text-xs truncate max-w-[280px]" title={filePath}>
              {filePath}
            </span>
          )}

          <span className="text-[10px] text-muted-foreground/60">
            ({lines.length} lines)
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {isLong && (
            <button
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="px-2 py-1 text-[11px] text-muted-foreground hover:text-gray-200 rounded hover:bg-surface2 transition-colors flex items-center gap-1"
              title={isCollapsed ? 'Expand code block' : 'Collapse code block'}
            >
              {isCollapsed ? (
                <><span>Expand</span><ChevronDown size={12} /></>
              ) : (
                <><span>Collapse</span><ChevronUp size={12} /></>
              )}
            </button>
          )}

          <button
            onClick={handleCopy}
            className="px-2.5 py-1 text-[11px] font-medium text-muted-foreground hover:text-[#D4AF37] rounded hover:bg-surface2 border border-transparent hover:border-border/60 transition-all flex items-center gap-1.5"
            title="Copy code"
          >
            {copied ? (
              <>
                <Check size={12} className="text-emerald-400" />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Copy size={12} />
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Code Body */}
      {!isCollapsed && (
        <div className="p-4 overflow-x-auto text-[13px] font-mono leading-relaxed max-h-[500px]">
          {isDiff ? (
            <div className="space-y-0.5">{renderDiffLines()}</div>
          ) : (
            <pre className="!m-0 !p-0 !bg-transparent !border-0 text-gray-200 overflow-visible">
              <code className={className} {...props}>
                {children}
              </code>
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
