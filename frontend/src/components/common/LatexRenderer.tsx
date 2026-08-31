import React, { useMemo, useState, useEffect } from 'react';
import katex from 'katex';
import { marked } from 'marked';
import { X } from 'lucide-react';

interface LatexRendererProps {
  content: string;
  className?: string;
}

export const LatexRenderer: React.FC<LatexRendererProps> = React.memo(({ content, className = '' }) => {
  const [lightboxImg, setLightboxImg] = useState<{ src: string; alt?: string } | null>(null);

  useEffect(() => {
    if (!lightboxImg) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setLightboxImg(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [lightboxImg]);

  const renderedHtml = useMemo(() => {
    if (!content) return '';

    let cleanContent = content;
    const trimmed = content.trim();
    if ((trimmed.startsWith('{') || trimmed.startsWith('```json')) && trimmed.includes('"explanation_markdown"')) {
      try {
        const jsonStr = trimmed.startsWith('```json') ? trimmed.split('```json')[1].split('```')[0].trim() : trimmed;
        const parsed = JSON.parse(jsonStr);
        if (parsed && typeof parsed === 'object') {
          cleanContent = parsed.explanation_markdown || parsed.explanation || cleanContent;
        }
      } catch (e) {
        const match = trimmed.match(/"explanation_markdown"\s*:\s*"(.*?)(?:"\s*,\s*"[a-zA-Z_]+"|\s*"\}|\s*"\s*$)/s);
        if (match) {
          cleanContent = match[1].replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\\\/g, '\\');
        }
      }
    }

    const mathTokens: { id: string; html: string }[] = [];
    let tokenIndex = 0;

    // 1. Extract and render Block Math $$...$$ using safe alphanumeric tokens (no underscores/asterisks)
    let text = cleanContent.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => {
      const tokenId = `KATEXBLOCKTOKEN${tokenIndex++}END`;
      let rendered = '';
      try {
        rendered = `<div class="my-4 text-center overflow-x-auto py-2.5 px-4 bg-surface-950 rounded-2xl border border-slate-800 shadow-inner">${katex.renderToString(
          math.trim(),
          { displayMode: true, throwOnError: false }
        )}</div>`;
      } catch (err) {
        rendered = `<div class="my-3 text-center text-xs font-mono text-rose-400 bg-surface-950 p-2 rounded">${math}</div>`;
      }
      mathTokens.push({ id: tokenId, html: rendered });
      return `\n\n${tokenId}\n\n`;
    });

    // 2. Extract and render Inline Math $...$ using safe alphanumeric tokens
    text = text.replace(/(?<!\\)\$([^\$\n]+?)(?<!\\)\$/g, (_, math) => {
      const tokenId = `KATEXINLINETOKEN${tokenIndex++}END`;
      let rendered = '';
      try {
        rendered = `<span class="inline-block px-1 font-serif text-indigo-200">${katex.renderToString(
          math.trim(),
          { displayMode: false, throwOnError: false }
        )}</span>`;
      } catch (err) {
        rendered = `<code class="text-xs text-rose-400">${math}</code>`;
      }
      mathTokens.push({ id: tokenId, html: rendered });
      return tokenId;
    });

    // 3. Configure marked with custom clean image renderer and GFM
    const renderer = new marked.Renderer();
    renderer.image = function (token: any) {
      const href = typeof token === 'object' ? token.href : arguments[0];
      const title = typeof token === 'object' ? token.title : arguments[1];
      const text = typeof token === 'object' ? token.text : arguments[2];
      const caption = text || title || '';
      return `\n<figure class="my-4 sm:float-right sm:ml-5 sm:mb-4 sm:mt-1 w-full sm:w-80 rounded-2xl overflow-hidden border border-slate-800 bg-surface-950 shadow-xl transition-all duration-300 hover:border-indigo-500/50 group clear-both sm:clear-none">\n  <div class="relative w-full overflow-hidden bg-slate-950 flex items-center justify-center min-h-[140px] max-h-[260px]">\n    <img src="${href}" alt="${caption}" class="w-full h-auto max-h-[260px] object-contain group-hover:scale-[1.03] transition-transform duration-500 ease-out block cursor-zoom-in" loading="lazy" />\n  </div>\n  ${caption ? `<figcaption class="px-3.5 py-2.5 text-[11px] text-slate-400 bg-surface-900/60 border-t border-slate-800/80 text-left font-sans flex items-start gap-2 leading-relaxed"><span class="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 shrink-0"></span><span class="text-slate-300 font-medium">${caption}</span></figcaption>` : ''}\n</figure>\n`;
    };

    marked.setOptions({
      gfm: true,
      breaks: true,
      renderer: renderer,
    });

    // 4. Parse Markdown into clean semantic HTML
    let html = marked.parse(text) as string;

    // 5. Restore KaTeX rendered math tokens
    for (const token of mathTokens) {
      html = html.replace(token.id, token.html);
    }

    return html;
  }, [content]);

  const handleContainerClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.tagName && target.tagName.toLowerCase() === 'img') {
      const img = target as HTMLImageElement;
      if (img.src) {
        setLightboxImg({
          src: img.src,
          alt: img.alt || '',
        });
      }
    }
  };

  return (
    <>
      <div
        className={`markdown-content ${className}`}
        onClick={handleContainerClick}
        dangerouslySetInnerHTML={{ __html: renderedHtml }}
      />

      {lightboxImg && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8 bg-black/90 backdrop-blur-md animate-fadeIn"
          onClick={() => setLightboxImg(null)}
        >
          <div
            className="relative max-w-5xl max-h-[90vh] flex flex-col items-center bg-surface-950 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl p-3 sm:p-5 animate-scaleUp"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setLightboxImg(null)}
              className="absolute top-4 right-4 z-10 p-2 rounded-full bg-surface-900/80 hover:bg-surface-800 border border-slate-700 text-slate-300 hover:text-white transition-colors cursor-pointer shadow-lg"
              title="Закрыть"
              aria-label="Закрыть"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="w-full flex items-center justify-center overflow-auto rounded-2xl bg-black/50 p-2">
              <img
                src={lightboxImg.src}
                alt={lightboxImg.alt || 'Illustration'}
                className="max-h-[75vh] w-auto max-w-full object-contain rounded-xl"
              />
            </div>
            {lightboxImg.alt && (
              <p className="mt-3 px-3 text-xs sm:text-sm text-slate-300 text-center font-medium leading-relaxed max-w-2xl">
                {lightboxImg.alt}
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
});
