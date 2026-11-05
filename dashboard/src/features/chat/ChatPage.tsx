import { useEffect, useRef } from "react"
import { useLocation, useNavigate, useSearchParams } from "react-router"
import { Composer } from "./Composer"
import { ConversationList } from "./ConversationList"
import { MessageList } from "./MessageList"
import { StatusLine } from "./StatusLine"
import { SuggestedPrompts } from "./SuggestedPrompts"
import { useChatStream } from "./useChatStream"
import { useMessages } from "./useMessages"

export function ChatPage() {
  const [params, setParams] = useSearchParams()
  const conversationId = params.get("conversation")
  const setConversationId = (id: string | null) =>
    setParams(id ? { conversation: id } : {}, { replace: true })
  const { data: messages = [], isLoading } = useMessages(conversationId)
  const {
    send,
    stop,
    regenerate,
    draft,
    activity,
    status,
    error,
    tokens,
    streaming,
  } = useChatStream(conversationId, setConversationId)
  const location = useLocation()
  const navigate = useNavigate()
  const queued = (location.state as { send?: string } | null)?.send
  const sent = useRef<string | null>(null)

  useEffect(() => {
    if (!queued || sent.current === location.key) return
    sent.current = location.key
    navigate(location.pathname + location.search, {
      replace: true,
      state: null,
    })
    void send(queued)
  }, [queued, location, navigate, send])

  return (
    <>
      <ConversationList
        selectedId={conversationId}
        onSelect={setConversationId}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-border px-6 py-3">
          <p className="flex items-center gap-2 text-[9px] font-medium tracking-[0.32em] uppercase text-muted-foreground">
            <span
              aria-hidden
              className="size-1 rotate-45 border border-ring/70"
            />
            Conversation
          </p>
          <p className="text-[9px] font-medium tracking-[0.32em] uppercase text-muted-foreground">
            Local model
          </p>
        </div>
        <MessageList
          messages={messages}
          loading={isLoading}
          draft={draft}
          activity={activity}
          status={status}
          onRegenerate={regenerate}
        />
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 p-4">
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!messages.length && !streaming && <SuggestedPrompts onPick={send} />}
          <Composer streaming={streaming} onSend={send} onStop={stop} />
          <StatusLine tokens={tokens} />
        </div>
      </main>
    </>
  )
}
