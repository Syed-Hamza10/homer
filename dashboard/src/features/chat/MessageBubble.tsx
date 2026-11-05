import { RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { CopyButton } from "./CopyButton"
import { LiveStatus } from "./LiveStatus"
import { Markdown } from "./Markdown"
import { SourceChips } from "./SourceChips"
import { splitSources } from "./sources"

type Props = {
  role: "user" | "assistant"
  content: string
  createdAt?: string
  stopped?: boolean
  pending?: boolean
  status?: string | null
  onRegenerate?: () => void
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

export function MessageBubble({
  role,
  content,
  createdAt,
  stopped,
  pending,
  status = null,
  onRegenerate,
}: Props) {
  const own = role === "user"
  const { body, sources } = own
    ? { body: content, sources: [] }
    : splitSources(content)
  const showActions = !own && !pending && content !== ""

  return (
    <div
      className={cn(
        "group flex flex-col gap-1",
        own ? "items-end" : "items-start",
        !createdAt && "animate-enter",
      )}
      data-testid={`message-${role}`}
    >
      <div
        className={cn(
          "max-w-[75%] rounded-md px-3.5 py-2.5 text-sm leading-relaxed",
          own
            ? "bg-primary whitespace-pre-wrap text-primary-foreground shadow-[inset_0_1px_0_oklch(1_0_0/0.12)]"
            : "min-w-0 border border-border bg-card/80 break-words shadow-[inset_0_1px_0_var(--marble-1)]",
        )}
      >
        {own ? content : body && <Markdown text={body} streaming={pending} />}
        {sources.length > 0 && <SourceChips sources={sources} />}
        {pending && (!content || status) && (
          <div className={cn(content && "mt-2")}>
            <LiveStatus text={status} />
          </div>
        )}
        {!pending && !own && !content && (
          <span className="text-muted-foreground">
            {stopped ? "Stopped before any reply." : "No reply."}
          </span>
        )}
      </div>
      {(showActions || stopped || createdAt) && (
        <div className="flex h-6 items-center gap-1 px-0.5 text-[10px] text-muted-foreground">
          {showActions && <CopyButton text={content} label="Copy message" />}
          {showActions && onRegenerate && (
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              aria-label="Regenerate"
              title="Regenerate"
              onClick={onRegenerate}
            >
              <RotateCcw strokeWidth={1.8} />
            </Button>
          )}
          {stopped && content && (
            <span className="tracking-[0.14em] uppercase">Stopped</span>
          )}
          {createdAt && (
            <time
              dateTime={createdAt}
              className="px-1 opacity-0 transition-opacity group-hover:opacity-100"
            >
              {formatTime(createdAt)}
            </time>
          )}
        </div>
      )}
    </div>
  )
}
