import React, { useMemo } from 'react';
import { Sparkles } from 'lucide-react';

interface SvgViewerProps {
  svgPayload: string;
  altText?: string;
  className?: string;
}

export const SvgViewer: React.FC<SvgViewerProps> = React.memo(({ svgPayload, altText, className = '' }) => {
  const sanitizedSvg = useMemo(() => {
    if (!svgPayload) return '';
    let svg = svgPayload.trim();

    // 1. Remove white/light background rects or replace with sleek dark/transparent
    svg = svg.replace(/<rect([^>]*?)fill=['"]#(?:fff|ffffff|f8fafc|f1f5f9|e2e8f0|white)['"]([^>]*?)\/?>/gi, (match, p1, p2) => {
      // If it's a full-size background rect (x=0, y=0 or width=100%/600), make it transparent/dark
      if (p1.includes('width') || p2.includes('width')) {
        return `<rect${p1}fill="transparent"${p2}/>`;
      }
      return match;
    });

    // 2. Replace dark text on dark backgrounds with clean light text
    svg = svg.replace(/fill=['"]#(?:000|000000|1e293b|0f172a|334155|black)['"]/gi, 'fill="#F1F5F9"');

    // 3. Ensure svg has style="background: transparent;"
    if (!svg.includes('background:')) {
      svg = svg.replace(/<svg\b([^>]*)>/i, '<svg$1 style="background: transparent; max-width: 100%;">');
    }

    return svg;
  }, [svgPayload]);

  if (!sanitizedSvg) return null;

  return (
    <figure className={`my-6 rounded-3xl overflow-hidden border border-slate-800 bg-surface-950 shadow-xl transition-all hover:border-indigo-500/40 ${className}`}>
      {/* Visual Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800 bg-surface-900">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-bold text-slate-200 tracking-wide uppercase">
            Интерактивная архитектурная схема
          </span>
        </div>
        {altText && (
          <span className="text-[11px] text-slate-400 font-normal max-w-xs truncate text-right">
            {altText}
          </span>
        )}
      </div>

      {/* SVG Container */}
      <div
        className="w-full flex justify-center items-center p-4 sm:p-6 bg-surface-950 overflow-x-auto [&>svg]:w-full [&>svg]:max-h-[380px] [&>svg]:h-auto transition-transform duration-300"
        dangerouslySetInnerHTML={{ __html: sanitizedSvg }}
      />
    </figure>
  );
});
