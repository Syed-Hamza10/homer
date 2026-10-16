import { useState } from "react"
import { Composer } from "./Composer"
import { ConversationList } from "./ConversationList"
import { MessageList } from "./MessageList"
import { StatusLine } from "./StatusLine"
import { useChatStream } from "./useChatStream"
import { useMessages } from "./useMessages"

export function ChatPage() {
  const [conversationId, setConversationId] = useState<string | null>(null)
  const { data: messages = [] } = useMessages(conversationId)
  const { send, draft, activity, error, tokens, streaming } = useChatStream(
    conversationId,
    setConversationId,
  )

  return (
    <>
      <ConversationList
        selectedId={conversationId}
        onSelect={setConversationId}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <MessageList messages={messages} draft={draft} activity={activity} />
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 p-4">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Composer disabled={streaming} onSend={send} />
          <StatusLine tokens={tokens} />
        </div>
      </main>
    </>
  )
}
