import { Paperclip } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EmailBody } from "./EmailBody"
import { displayName, fileSize, longDate } from "./format"
import type { Message } from "./types"

type Props = {
  message: Message
  timeZone: string
  showImages: boolean
  onShowImages: () => void
}

export function MessageView({
  message,
  timeZone,
  showImages,
  onShowImages,
}: Props) {
  return (
    <article
      data-testid={`message-${message.id}`}
      className="flex flex-col gap-3 rounded-lg border border-border bg-card/60 p-4 shadow-[inset_0_1px_0_var(--marble-1)]"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex min-w-0 flex-col gap-0.5">
          <p className="truncate text-sm font-medium" title={message.sender}>
            {displayName(message.sender)}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {message.sender.match(/<([^>]+)>/)?.[1] ?? ""}
            </span>
          </p>
          <p className="truncate text-xs text-muted-foreground">
            To: {message.to}
          </p>
          {message.cc && (
            <p className="truncate text-xs text-muted-foreground">
              Cc: {message.cc}
            </p>
          )}
        </div>
        <p className="shrink-0 text-xs text-muted-foreground tabular-nums">
          {message.received_at
            ? longDate(message.received_at, timeZone)
            : message.date}
        </p>
      </header>
      {message.remote_images > 0 && !showImages && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
          <span>
            Images from the web are hidden so the sender cannot see you opened
            this.
          </span>
          <Button size="xs" variant="outline" onClick={onShowImages}>
            Show images
          </Button>
        </div>
      )}
      {message.body_html ? (
        <EmailBody html={message.body_html} showImages={showImages} />
      ) : (
        <p
          data-testid="message-text"
          className="text-sm leading-relaxed break-words whitespace-pre-wrap"
        >
          {message.body_text}
        </p>
      )}
      {message.attachments.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {message.attachments.map((attachment) => (
            <li
              key={attachment.filename}
              className="flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs"
            >
              <Paperclip className="size-3.5 text-muted-foreground" />
              {attachment.filename}
              <span className="text-muted-foreground">
                {fileSize(attachment.size)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </article>
  )
}
