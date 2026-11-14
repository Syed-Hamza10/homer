import { useEffect, useRef, useState } from "react"
import { useLocation, useNavigate, useSearchParams } from "react-router"
import { ErrorNotice } from "@/components/ErrorNotice"
import { useConversationApprovals } from "@/features/approvals/useConversationApprovals"
import { Composer } from "./Composer"
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
  const { data: approvals = [] } = useConversationApprovals(conversationId)
  const {
    send,
    stop,
    retry,
    regenerate,
    draft,
    failed,
    activity,
    status,
    error,
    tokens,
    streaming,
  } = useChatStream(conversationId, setConversationId)
  const [text, setText] = useState("")
  const viewing = useRef(conversationId)
  const location = useLocation()
  const navigate = useNavigate()
  const queued = (location.state as { send?: string } | null)?.send
  const sent = useRef<string | null>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const empty =
    !conversationId && !messages.length && !streaming && failed === null

  useEffect(() => {
    viewing.current = conversationId
  }, [conversationId])

  const keepOnFailure = (message: string, sent: Promise<boolean>) => {
    const origin = conversationId
    void sent.then((ok) => {
      if (!ok && viewing.current === origin) setText((t) => t || message)
    })
  }

  const submit = (message: string) => keepOnFailure(message, send(message))

  const tryAgain = () => {
    if (failed === null) return
    if (text.trim() === failed) setText("")
    keepOnFailure(failed, retry())
  }

  useEffect(() => {
    if (!queued || sent.current === location.key) return
    sent.current = location.key
    navigate(location.pathname + location.search, {
      replace: true,
      state: null,
    })
    void send(queued)
  }, [queued, location, navigate, send])

  const composer = (
    <>
      <ErrorNotice
        error={error}
        onRetry={
          failed !== null
            ? tryAgain
            : conversationId
              ? () => void regenerate()
              : undefined
        }
        className="px-2"
      />
      <Composer
        streaming={streaming}
        onSend={submit}
        onStop={stop}
        inputRef={input}
        value={text}
        onValueChange={setText}
      />
    </>
  )

  if (empty)
    return (
      <main className="flex min-w-0 flex-1 flex-col items-center justify-center px-5 pb-[12vh]">
        <div className="flex w-full max-w-2xl flex-col gap-5">
          <h1 className="text-center font-heading text-[2rem] leading-tight tracking-tight">
            What can I do for you?
          </h1>
          {composer}
          <SuggestedPrompts onPick={send} />
        </div>
      </main>
    )

  return (
    <main className="flex min-w-0 flex-1 flex-col">
      <MessageList
        messages={messages}
        approvals={approvals}
        loading={isLoading}
        draft={draft}
        activity={activity}
        status={status}
        failed={failed}
        onRegenerate={regenerate}
        onRetry={tryAgain}
        onChoose={(card, option) =>
          void send(option.label, {
            question_id: card.question_id,
            option_id: option.id,
          })
        }
        onOther={() => input.current?.focus()}
      />
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-2 px-5 pt-1 pb-4">
        {composer}
        <StatusLine tokens={tokens} />
      </div>
    </main>
  )
}
