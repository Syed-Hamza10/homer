import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { ApiError, streamSse } from "@/lib/api"
import type {
  ActivityItem,
  ApprovalRequiredEvent,
  DoneEvent,
  ErrorEvent,
  MetaEvent,
  TokenEvent,
  ToolCallEvent,
  ToolResultEvent,
} from "./types"
import { conversationsKey } from "./useConversations"

type Draft = { user: string; assistant: string }
type Run = { conversation: string | null; items: ActivityItem[] }

export function useChatStream(
  conversationId: string | null,
  onConversation: (id: string) => void,
) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [run, setRun] = useState<Run>({ conversation: null, items: [] })
  const [error, setError] = useState<string | null>(null)
  const [tokens, setTokens] = useState(0)

  const add = (item: ActivityItem) =>
    setRun((r) => ({ ...r, items: [...r.items, item] }))

  const send = async (message: string) => {
    setError(null)
    setRun({ conversation: conversationId, items: [] })
    setDraft({ user: message, assistant: "" })
    const body = conversationId
      ? { conversation_id: conversationId, message }
      : { message }
    try {
      await streamSse("/api/chat", body, {
        meta: (data) => {
          const { conversation_id } = data as MetaEvent
          setRun((r) => ({ ...r, conversation: conversation_id }))
          if (conversation_id !== conversationId)
            onConversation(conversation_id)
        },
        token: (data) => {
          const { text } = data as TokenEvent
          setDraft((d) => d && { ...d, assistant: d.assistant + text })
        },
        tool_call: (data) =>
          add({ kind: "tool_call", ...(data as ToolCallEvent) }),
        tool_result: (data) =>
          add({ kind: "tool_result", ...(data as ToolResultEvent) }),
        approval_required: (data) =>
          add({ kind: "approval", ...(data as ApprovalRequiredEvent) }),
        done: (data) => {
          const { input_tokens, output_tokens } = data as DoneEvent
          setTokens((n) => n + input_tokens + output_tokens)
        },
        error: (data) => setError((data as ErrorEvent).message),
      })
    } catch (e) {
      setError(
        e instanceof ApiError
          ? `Request failed (${e.status})`
          : "Connection lost",
      )
    }
    await queryClient.invalidateQueries({ queryKey: conversationsKey })
    setDraft(null)
  }

  const activity = run.conversation === conversationId ? run.items : []
  return { send, draft, activity, error, tokens, streaming: draft !== null }
}
