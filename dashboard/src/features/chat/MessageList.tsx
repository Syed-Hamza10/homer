import { useEffect, useRef } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { MessageBubble } from "./MessageBubble"
import type { Message } from "./types"

type Props = {
  messages: Message[]
  draft: { user: string; assistant: string } | null
}

export function MessageList({ messages, draft }: Props) {
  const end = useRef<HTMLDivElement>(null)
  const last = messages.at(-1)
  const showDraftUser =
    draft && !(last?.role === "user" && last.content === draft.user)

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" })
  }, [messages, draft])

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="mx-auto flex max-w-3xl flex-col gap-3 p-4">
        {messages.map((m) => (
          <MessageBubble key={m.id} role={m.role} content={m.content} />
        ))}
        {showDraftUser && <MessageBubble role="user" content={draft.user} />}
        {draft && <MessageBubble role="assistant" content={draft.assistant} />}
        <div ref={end} />
      </div>
    </ScrollArea>
  )
}
