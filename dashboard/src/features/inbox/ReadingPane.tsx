import { ArrowLeft, X } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useShortcuts } from "@/lib/shortcuts"
import { errorText } from "@/lib/errorText"
import { MailComposer } from "./MailComposer"
import { MessageView } from "./MessageView"
import { ThreadActions } from "./ThreadActions"
import type { ComposeDraft, ReplyMode } from "./types"
import {
  useFollowUp,
  useLabelChange,
  useReplyDraft,
  useThread,
} from "./useMail"

type Props = {
  threadId: string
  timeZone: string
  userLabels: string[]
  shortcuts: boolean
  onClose: () => void
}

const replyTitles: Record<ReplyMode, string> = {
  reply: "Reply",
  reply_all: "Reply all",
  forward: "Forward",
}

export function ReadingPane({
  threadId,
  timeZone,
  userLabels,
  shortcuts,
  onClose,
}: Props) {
  const [showImages, setShowImages] = useState(false)
  const [composer, setComposer] = useState<{
    draft: ComposeDraft
    title: string
  } | null>(null)
  const thread = useThread(threadId, showImages)
  const change = useLabelChange()
  const reply = useReplyDraft(threadId)
  const messages = thread.data?.messages ?? []
  const latest = messages.at(-1)
  const followUp = useFollowUp(latest?.id ?? "")
  const labels = [...new Set(messages.flatMap((message) => message.labels))]
  const shownLabels = labels.filter((name) => userLabels.includes(name))
  const error = change.error ?? reply.error ?? followUp.error
  const update = (add: string[], remove: string[], then?: () => void) =>
    change.mutate({ threadId, add, remove }, { onSuccess: then })
  const openReply = (mode: ReplyMode) =>
    reply.mutate(mode, {
      onSuccess: (draft) => setComposer({ draft, title: replyTitles[mode] }),
    })
  const starred = labels.includes("STARRED")
  useShortcuts(
    shortcuts && thread.data
      ? {
          e: () => update([], ["INBOX"], onClose),
          s: () =>
            starred ? update([], ["STARRED"]) : update(["STARRED"], []),
          r: () => openReply("reply"),
          a: () => openReply("reply_all"),
          f: () => openReply("forward"),
          "Shift+I": () => update([], ["UNREAD"]),
          "Shift+U": () => update(["UNREAD"], [], onClose),
        }
      : {},
  )

  return (
    <section
      data-testid="reading-pane"
      aria-label="Conversation"
      className="flex min-h-0 flex-1 flex-col"
    >
      <header className="flex flex-col gap-3 border-b border-border px-4 py-3">
        <div className="flex items-start gap-2">
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Back to list"
            className="lg:hidden"
            onClick={onClose}
          >
            <ArrowLeft />
          </Button>
          <h2 className="min-w-0 flex-1 font-heading text-xl leading-snug">
            {thread.data?.subject ||
              (thread.isPending ? "Loading…" : "(no subject)")}
          </h2>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Close conversation"
            className="hidden lg:inline-flex"
            onClick={onClose}
          >
            <X />
          </Button>
        </div>
        {shownLabels.length > 0 && (
          <ul className="flex flex-wrap gap-1.5">
            {shownLabels.map((name) => (
              <li
                key={name}
                className="flex items-center gap-1 rounded-sm border border-border bg-muted px-1.5 py-0.5 text-[10px] tracking-[0.08em] uppercase text-muted-foreground"
              >
                {name}
                <button
                  type="button"
                  aria-label={`Remove label ${name}`}
                  onClick={() => update([], [name])}
                >
                  <X className="size-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
        {thread.data && (
          <ThreadActions
            labels={labels}
            userLabels={userLabels}
            busy={change.isPending || reply.isPending}
            onReply={openReply}
            onChange={(add, remove) => update(add, remove)}
            onMarkUnread={() => update(["UNREAD"], [], onClose)}
            onArchive={() => update([], ["INBOX"], onClose)}
          />
        )}
        {error && (
          <p className="text-sm text-destructive">{errorText(error)}</p>
        )}
      </header>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
        {thread.error && (
          <p className="text-sm text-destructive">{errorText(thread.error)}</p>
        )}
        {messages.map((message) => (
          <MessageView
            key={message.id}
            message={message}
            timeZone={timeZone}
            showImages={showImages}
            onShowImages={() => setShowImages(true)}
          />
        ))}
        {latest && !composer && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="xs"
              variant="ghost"
              disabled={followUp.isPending}
              onClick={() => followUp.mutate()}
            >
              Remind me to follow up
            </Button>
            {followUp.data && (
              <span className="text-xs text-muted-foreground">
                Follow-up due{" "}
                {new Date(followUp.data.due_at).toLocaleDateString([], {
                  timeZone,
                })}
                .
              </span>
            )}
          </div>
        )}
        {composer && (
          <MailComposer
            key={composer.title}
            initial={composer.draft}
            title={composer.title}
            onClose={() => setComposer(null)}
          />
        )}
      </div>
    </section>
  )
}
