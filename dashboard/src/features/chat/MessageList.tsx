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

export function MessageList({ messages, draft, activity }: Props) {
  const end = useRef<HTMLDivElement>(null)
  const last = messages.at(-1)
  const showDraftUser =
    draft && !(last?.role === "user" && last.content === draft.user)
  const answered = !draft && activity.length > 0 && last?.role === "assistant"
  const shown = answered ? messages.slice(0, -1) : messages

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
