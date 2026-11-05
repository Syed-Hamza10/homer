import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import { CopyButton } from "./CopyButton"
import { rehypeStreamWords } from "./streamWords"

type Node = { type: string; value?: string; children?: Node[] }

function textOf(node: Node | undefined): string {
  if (!node) return ""
  if (node.type === "text") return node.value ?? ""
  return (node.children ?? []).map(textOf).join("")
}

const components: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-ring underline underline-offset-2 hover:text-foreground"
    >
      {children}
    </a>
  ),
  ul: ({ children }) => (
    <ul className="mb-2 list-disc pl-5 last:mb-0 [&_ul]:mb-0">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-2 list-decimal pl-5 last:mb-0 [&_ol]:mb-0">{children}</ol>
  ),
  li: ({ children }) => <li className="mt-0.5">{children}</li>,
  h1: ({ children }) => (
    <h3 className="mb-2 font-heading text-base font-semibold">{children}</h3>
  ),
  h2: ({ children }) => (
    <h3 className="mb-2 font-heading text-base font-semibold">{children}</h3>
  ),
  h3: ({ children }) => (
    <h4 className="mb-1.5 text-sm font-semibold">{children}</h4>
  ),
  blockquote: ({ children }) => (
    <blockquote className="mb-2 border-l-2 border-border pl-3 text-muted-foreground">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="mb-2 overflow-x-auto">
      <table className="text-left text-xs [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1">
        {children}
      </table>
    </div>
  ),
  code: ({ className, children }) => (
    <code
      className={
        className ?? "rounded-sm bg-muted px-1 py-0.5 font-mono text-[0.85em]"
      }
    >
      {children}
    </code>
  ),
  pre: ({ node, children }) => (
    <div
      className="group/code relative mb-2 last:mb-0"
      data-testid="code-block"
    >
      <CopyButton
        text={textOf(node?.children[0]).replace(/\n$/, "")}
        label="Copy code"
        className="absolute top-1 right-1 bg-card/80"
      />
      <pre className="overflow-x-auto rounded-md border border-border bg-muted/60 p-3 pr-9 font-mono text-xs leading-relaxed">
        {children}
      </pre>
    </div>
  ),
}

type Props = { text: string; streaming?: boolean }

export function Markdown({ text, streaming = false }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={streaming ? [rehypeStreamWords] : []}
      components={components}
    >
      {text}
    </ReactMarkdown>
  )
}
