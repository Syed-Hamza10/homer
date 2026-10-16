import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { ApiError, streamSse } from "@/lib/api"
import type { DoneEvent, ErrorEvent, MetaEvent, TokenEvent } from "./types"
import { conversationsKey } from "./useConversations"

type Draft = { user: string; assistant: string }

export function useChatStream(
  conversationId: string | null,
  onConversation: (id: string) => void,
) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tokens, setTokens] = useState(0)

  const send = async (message: string) => {
    setError(null)
    setDraft({ user: message, assistant: "" })
    const body = conversationId
      ? { conversation_id: conversationId, message }
      : { message }
    try {
      await streamSse("/api/chat", body, {
        meta: (data) => {
          const { conversation_id } = data as MetaEvent
          if (conversation_id !== conversationId)
            onConversation(conversation_id)
        },
        token: (data) => {
          const { text } = data as TokenEvent
          setDraft((d) => d && { ...d, assistant: d.assistant + text })
        },
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

  return { send, draft, error, tokens, streaming: draft !== null }
}
