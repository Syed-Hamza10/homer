import { useEffect, useRef } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ActivityLine } from "./ActivityLine"
import { MessageBubble } from "./MessageBubble"
import type { ActivityItem, Message } from "./types"

type Props = {
  messages: Message[]
  draft: { user: string; assistant: string } | null
  activity: ActivityItem[]
}

function draftStart(messages: Message[], user: string): number {
  for (let index = messages.length - 1; index >= 0; index--) {
    const message = messages[index]
    if (message.role === "user" && message.content === user) return index
  }
  return -1
}

export function MessageList({ messages, draft, activity }: Props) {
  const end = useRef<HTMLDivElement>(null)
  const start = draft ? draftStart(messages, draft.user) : -1
  const stored = draft && start >= 0 ? messages.slice(0, start + 1) : messages
  const last = stored.at(-1)
  const showDraftUser = draft && start < 0
  const answered = !draft && activity.length > 0 && last?.role === "assistant"
  const shown = answered ? stored.slice(0, -1) : stored

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" })
  }, [messages, draft, activity])

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="mx-auto flex max-w-3xl flex-col gap-3 p-4">
        {shown.map((m) => (
          <MessageBubble key={m.id} role={m.role} content={m.content} />
        ))}
        {showDraftUser && <MessageBubble role="user" content={draft.user} />}
        {activity.map((item, index) => (
          <ActivityLine key={index} item={item} />
        ))}
        {answered && last && (
          <MessageBubble role={last.role} content={last.content} />
        )}
        {draft && <MessageBubble role="assistant" content={draft.assistant} />}
        <div ref={end} />
      </div>
    </ScrollArea>
  )
}
