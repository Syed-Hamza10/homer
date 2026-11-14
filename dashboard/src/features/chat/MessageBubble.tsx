import { RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { CopyButton } from "./CopyButton"
import { LiveStatus } from "./LiveStatus"
import { Markdown } from "./Markdown"
import { SourceChips } from "./SourceChips"
import { splitSources } from "./sources"
import { stripUntrusted } from "./untrusted"

type Props = {
  role: "user" | "assistant"
  content: string
  createdAt?: string
  stopped?: boolean
  pending?: boolean
  quiet?: boolean
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
  quiet = false,
  onRegenerate,
}: Props) {
  const own = role === "user"
  const { body, sources } = own
    ? { body: content, sources: [] }
    : splitSources(stripUntrusted(content))
  const showActions = !own && !pending && content !== ""

  return (
    <div
      className={cn(
        "group flex flex-col gap-1.5",
        own ? "items-end" : "items-stretch",
        !createdAt && "animate-enter",
      )}
      data-testid={`message-${role}`}
    >
      <div
        className={cn(
          "text-[15px] leading-7",
          own
            ? "max-w-[80%] rounded-2xl rounded-br-md bg-secondary px-4 py-2 whitespace-pre-wrap text-secondary-foreground"
            : "min-w-0 break-words",
        )}
      >
        {own ? content : body && <Markdown text={body} streaming={pending} />}
        {sources.length > 0 && <SourceChips sources={sources} />}
        {pending && !content && !quiet && <LiveStatus />}
        {!pending && !own && !content && (
          <span className="text-muted-foreground">
            {stopped ? "Stopped before any reply." : "No reply."}
          </span>
        )}
      </div>
      {(showActions || stopped || createdAt) && (
        <div
          className={cn(
            "-mt-1 flex h-6 items-center gap-1 text-[11px] text-muted-foreground opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100",
            own ? "pr-1" : "-ml-1",
            stopped && "opacity-100",
          )}
        >
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
          {stopped && content && <span>Stopped</span>}
          {createdAt && (
            <time dateTime={createdAt} className="px-1">
              {formatTime(createdAt)}
            </time>
          )}
        </div>
      )}
    </div>
  )
}
