import React, { useEffect, useId, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import mermaid from 'mermaid';

// One-time engine setup; theme follows the app's dark class at init time.
mermaid.initialize({
  startOnLoad: false,
  theme: document.documentElement.classList.contains('dark') ? 'dark' : 'neutral',
  securityLevel: 'loose',
  fontFamily: 'Inter, system-ui, sans-serif',
});

/** Renders a ```mermaid code block as an SVG diagram, falling back to the raw
 * code (styled) whenever the definition fails to parse. */
const MermaidBlock: React.FC<{ code: string }> = ({ code }) => {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const reactId = useId().replace(/[^a-zA-Z0-9]/g, '');

  useEffect(() => {
    let alive = true;
    setFailed(false);
    mermaid
      .render(`mmd-${reactId}`, code)
      .then(({ svg: out }) => {
        if (alive) setSvg(out);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [code, reactId]);

  if (failed || !svg) {
    return (
      <pre className="overflow-x-auto rounded-lg border border-border bg-secondary/50 p-3 font-mono text-xs">
        {code}
      </pre>
    );
  }
  return (
    <div
      className="my-2 flex justify-center overflow-x-auto rounded-lg border border-border bg-secondary/30 p-3 [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
};

interface Props {
  text: string;
  /** While an answer is still streaming, mermaid blocks stay as code so a
   * half-received definition never flashes parse errors. */
  streaming?: boolean;
}

/** Professional markdown rendering for AI answers: GFM tables, task-list
 * checklists, numbered procedures, headings — and Mermaid diagrams. */
export const MarkdownContent: React.FC<Props> = ({ text, streaming = false }) => (
  <div className="space-y-2 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: (p) => <h3 className="mt-3 text-base font-semibold" {...p} />,
        h2: (p) => <h4 className="mt-3 text-sm font-semibold" {...p} />,
        h3: (p) => <h5 className="mt-2 text-sm font-semibold" {...p} />,
        p: (p) => <p className="my-1.5 leading-relaxed" {...p} />,
        ul: (p) => <ul className="my-1.5 list-disc space-y-1 pl-5" {...p} />,
        ol: (p) => <ol className="my-1.5 list-decimal space-y-1 pl-5" {...p} />,
        li: (p) => <li className="leading-relaxed" {...p} />,
        a: (p) => (
          <a
            className="text-primary underline underline-offset-2"
            target="_blank"
            rel="noreferrer"
            {...p}
          />
        ),
        blockquote: (p) => (
          <blockquote
            className="my-2 border-l-2 border-primary/50 pl-3 text-foreground/80"
            {...p}
          />
        ),
        table: (p) => (
          <div className="my-2 overflow-x-auto rounded-lg border border-border">
            <table className="w-full border-collapse text-xs" {...p} />
          </div>
        ),
        thead: (p) => <thead className="bg-secondary/70" {...p} />,
        th: (p) => (
          <th
            className="border-b border-border px-3 py-2 text-left font-semibold"
            {...p}
          />
        ),
        td: (p) => (
          <td className="border-b border-border/50 px-3 py-1.5 align-top" {...p} />
        ),
        input: (p) => <input className="mr-1.5 accent-primary" {...p} />,
        hr: () => <hr className="my-3 border-border" />,
        code: ({ className, children, ...rest }) => {
          const match = /language-(\w+)/.exec(className || '');
          const raw = String(children).replace(/\n$/, '');
          if (match?.[1] === 'mermaid' && !streaming) {
            return <MermaidBlock code={raw} />;
          }
          if (match) {
            return (
              <pre className="my-2 overflow-x-auto rounded-lg border border-border bg-secondary/50 p-3 font-mono text-xs">
                <code {...rest}>{raw}</code>
              </pre>
            );
          }
          return (
            <code
              className="rounded bg-secondary/70 px-1 py-0.5 font-mono text-[0.85em]"
              {...rest}
            >
              {children}
            </code>
          );
        },
      }}
    >
      {text}
    </ReactMarkdown>
  </div>
);
