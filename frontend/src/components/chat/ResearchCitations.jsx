/**
 * ResearchCitations — renders structured citations below a Deep Research answer.
 * Supports web (URL), PDF (file + page), and finance source types.
 */
export default function ResearchCitations({ citations = [] }) {
  if (!citations || citations.length === 0) return null;

  const sourceIcon = (type) => ({
    web: '🌐',
    pdf: '📄',
    finance: '💹',
    news: '📰',
  }[type] || '🔗');

  return (
    <div className="mt-3 border-t border-[#C5A880]/10 pt-3">
      <div className="text-[11px] font-semibold text-[#A8A49A] uppercase tracking-wider mb-2">
        Research Sources
      </div>
      <div className="space-y-1.5">
        {citations.map((cit, idx) => (
          <div key={cit.citation_id || idx} className="flex items-start gap-2 text-[12px]">
            <span className="text-[#D4AF37] shrink-0 font-mono text-[11px] mt-0.5">[{idx + 1}]</span>
            <span>{sourceIcon(cit.source_type)}</span>
            <div className="flex-1 min-w-0">
              {cit.url ? (
                <a
                  href={cit.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#D4AF37] hover:underline truncate block"
                  title={cit.url}
                >
                  {cit.title || cit.url}
                </a>
              ) : (
                <span className="text-gray-300">
                  {cit.title || 'Source'}
                  {cit.page_number ? ` — Page ${cit.page_number}` : ''}
                </span>
              )}
              {cit.published_at && (
                <span className="text-[#A8A49A] text-[10px] ml-1">· {cit.published_at}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
