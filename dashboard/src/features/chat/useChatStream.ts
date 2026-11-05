import { useQueryClient } from "@tanstack/react-query"
import { useRef, useState } from "react"
import { ApiError, postJson, streamSse } from "@/lib/api"
import type {
  ActivityItem,
  ApprovalRequiredEvent,
  DoneEvent,
  ErrorEvent,
  GoogleReconnectEvent,
  MetaEvent,
  ReplaceEvent,
  StatusEvent,
  TokenEvent,
  ToolCallEvent,
  ToolResultEvent,
} from "./types"
import { conversationsKey } from "./useConversations"

type Draft = { user: string; assistant: string }
type Run = { conversation: string | null; items: ActivityItem[] }

const SAVE_GRACE_MS = 300

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export function useChatStream(
  conversationId: string | null,
  onConversation: (id: string) => void,
) {
  const queryClient = useQueryClient()
  const controller = useRef<AbortController | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [run, setRun] = useState<Run>({ conversation: null, items: [] })
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tokens, setTokens] = useState(0)

  const add = (item: ActivityItem) =>
    setRun((r) => ({ ...r, items: [...r.items, item] }))

  const send = async (message: string) => {
    const abort = new AbortController()
    controller.current = abort
    setError(null)
    setStatus(null)
    setRun({ conversation: conversationId, items: [] })
    setDraft({ user: message, assistant: "" })
    const body = conversationId
      ? { conversation_id: conversationId, message }
      : { message }
    try {
      await streamSse(
        "/api/chat",
        body,
        {
          meta: (data) => {
            const { conversation_id } = data as MetaEvent
            setRun((r) => ({ ...r, conversation: conversation_id }))
            if (conversation_id !== conversationId)
              onConversation(conversation_id)
          },
          status: (data) => setStatus((data as StatusEvent).text),
          token: (data) => {
            const { text } = data as TokenEvent
            setStatus(null)
            setDraft((d) => d && { ...d, assistant: d.assistant + text })
          },
          replace: (data) => {
            const { text } = data as ReplaceEvent
            setDraft((d) => d && { ...d, assistant: text })
          },
          tool_call: (data) =>
            add({ kind: "tool_call", ...(data as ToolCallEvent) }),
          tool_result: (data) =>
            add({ kind: "tool_result", ...(data as ToolResultEvent) }),
          approval_required: (data) =>
            add({ kind: "approval", ...(data as ApprovalRequiredEvent) }),
          google_reconnect: (data) =>
            add({ kind: "reconnect", ...(data as GoogleReconnectEvent) }),
          done: (data) => {
            const { input_tokens, output_tokens } = data as DoneEvent
            setTokens((n) => n + input_tokens + output_tokens)
          },
          error: (data) => setError((data as ErrorEvent).message),
        },
        abort.signal,
      )
    } catch (e) {
      if (abort.signal.aborted) await wait(SAVE_GRACE_MS)
      else
        setError(
          e instanceof ApiError
            ? `Request failed (${e.status})`
            : "Connection lost",
        )
    }
    controller.current = null
    await queryClient.invalidateQueries({ queryKey: conversationsKey })
    setStatus(null)
    setDraft(null)
  }

  const stop = () => controller.current?.abort()

  const regenerate = async () => {
    if (!conversationId) return
    try {
      const { message } = await postJson<{ message: string }>(
        `/api/conversations/${conversationId}/regenerate`,
        {},
      )
      await send(message)
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? "This reply cannot be regenerated"
          : "Could not regenerate the reply",
      )
    }
  }

  const activity = run.conversation === conversationId ? run.items : []
  return {
    send,
    stop,
    regenerate,
    draft,
    activity,
    status,
    error,
    tokens,
    streaming: draft !== null,
  }
}
