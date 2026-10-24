import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Check, Copy } from "lucide-react";

function CodeBlock({ children }: { children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);

  const copy = (e: React.MouseEvent<HTMLButtonElement>) => {
    const pre = e.currentTarget.closest("[data-code-wrap]")?.querySelector("pre");
    const text = pre?.textContent ?? "";
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div data-code-wrap className="group relative my-2 overflow-hidden rounded-md border border-border">
      <div className="flex items-center justify-between border-b border-border/60 bg-[#0d1117] px-3 py-1">
        <span className="text-[10px] uppercase tracking-wider text-neutral-500">code</span>
        <button
          onClick={copy}
          className="flex items-center gap-1 rounded p-1 text-neutral-400 opacity-0 transition-opacity hover:text-neutral-200 group-hover:opacity-100"
          title="Copy code"
        >
          {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
        </button>
      </div>
      <pre className="overflow-x-auto bg-[#0d1117] p-3 text-[12.5px] leading-relaxed text-neutral-200">
        {children}
      </pre>
    </div>
  );
}

export const Markdown = memo(function Markdown({ content }: { content: string }) {
  return (
    <div className="prose-sm min-w-0 break-words text-[14px] leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          a: (props) => <a {...props} target="_blank" rel="noreferrer" className="text-accent underline" />,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-[13px]">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-border px-2.5 py-1.5 text-left font-medium">{children}</th>
          ),
          td: ({ children }) => <td className="border-b border-border/50 px-2.5 py-1.5">{children}</td>,
          code: ({ className, children, ...props }) => {
            if (className) {
              return (
                <code className={className} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className="rounded bg-border/40 px-1 py-0.5 font-mono text-[12.5px]" {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
