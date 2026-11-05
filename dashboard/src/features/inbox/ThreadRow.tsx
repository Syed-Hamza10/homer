import { Paperclip, Star } from "lucide-react"
import { useEffect, useRef } from "react"
import { cn } from "@/lib/utils"
import { displayName, shortDate } from "./format"
import type { ThreadSummary } from "./types"

type Props = {
  thread: ThreadSummary
  timeZone: string
  selected: boolean
  focused: boolean
  sentView: boolean
  onOpen: () => void
}

export function ThreadRow({
  thread,
  timeZone,
  selected,
  focused,
  sentView,
  onOpen,
}: Props) {
  const row = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (focused) row.current?.scrollIntoView?.({ block: "nearest" })
  }, [focused])
  const who = sentView
    ? `To: ${displayName(thread.to)}`
    : displayName(thread.sender)

  return (
    <li>
      <button
        ref={row}
        type="button"
        data-testid={`thread-${thread.id}`}
        data-focused={focused ? "true" : undefined}
        aria-current={selected ? "true" : undefined}
        onClick={onOpen}
        className={cn(
          "flex w-full flex-col gap-0.5 border-b border-border/70 px-3 py-2.5 text-left transition-colors hover:bg-muted/40",
          selected && "bg-muted/70 shadow-[inset_2px_0_0_var(--ring)]",
          focused && !selected && "bg-muted/40 ring-1 ring-ring/40 ring-inset",
        )}
      >
        <span className="flex items-center gap-2">
          <span
            className={cn(
              "min-w-0 flex-1 truncate text-sm",
              thread.unread ? "font-semibold" : "text-muted-foreground",
            )}
          >
            {who}
            {thread.message_count > 1 && (
              <span className="ml-1 text-xs font-normal text-muted-foreground">
                {thread.message_count}
              </span>
            )}
          </span>
          {thread.has_attachment && (
            <Paperclip
              aria-label="Has attachment"
              className="size-3.5 text-muted-foreground"
            />
          )}
          {thread.starred && (
            <Star
              aria-label="Starred"
              className="size-3.5 fill-current text-amber-500"
            />
          )}
          {thread.received_at && (
            <span
              className={cn(
                "shrink-0 text-xs tabular-nums",
                thread.unread ? "font-semibold" : "text-muted-foreground",
              )}
            >
              {shortDate(thread.received_at, timeZone)}
            </span>
          )}
        </span>
        <span
          className={cn("truncate text-sm", thread.unread && "font-semibold")}
        >
          {thread.subject || "(no subject)"}
        </span>
        <span className="truncate text-xs text-muted-foreground">
          {thread.snippet}
        </span>
      </button>
    </li>
  )
}
