import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

interface MermaidViewerProps {
  chart: string;
  className?: string;
}

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    darkMode: true,
    background: '#0f172a',
    primaryColor: '#6366f1',
    primaryTextColor: '#f8fafc',
    primaryBorderColor: '#4f46e5',
    lineColor: '#64748b',
    secondaryColor: '#10b981',
    tertiaryColor: '#1e293b',
  },
  securityLevel: 'loose',
});

export const MermaidViewer: React.FC<MermaidViewerProps> = ({ chart, className = '' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const renderDiagram = async () => {
      if (!chart.trim()) return;
      try {
        setError(null);
        const uniqueId = `mermaid-${Math.random().toString(36).substring(2, 9)}`;
        const { svg } = await mermaid.render(uniqueId, chart);
        if (isMounted) {
          setSvgContent(svg);
        }
      } catch (err: any) {
        console.error('Mermaid render error:', err);
        if (isMounted) {
          setError('Failed to render curriculum graph.');
        }
      }
    };

    renderDiagram();

    return () => {
      isMounted = false;
    };
  }, [chart]);

  if (error) {
    return <div className="text-xs text-rose-400 p-2 bg-rose-950/40 rounded">{error}</div>;
  }

  return (
    <div
      ref={containerRef}
      className={`overflow-x-auto flex justify-center items-center py-3 bg-surface-900/60 rounded-xl border border-slate-800/80 shadow-inner ${className}`}
      dangerouslySetInnerHTML={{ __html: svgContent }}
    />
  );
};
