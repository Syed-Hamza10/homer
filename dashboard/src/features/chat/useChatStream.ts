import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef } from "react"
import { ApiError, postJson, streamSse } from "@/lib/api"
import type {
  ActivityItem,
  ApprovalRequiredEvent,
  ChoiceEvent,
  ChoiceHint,
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
import { approvalsKey } from "@/features/approvals/useApprovals"
import { conversationsKey } from "./useConversations"
import {
  NEW_CHAT,
  addTokens,
  idle,
  isLive,
  moveStream,
  patchStream,
  type Stream,
  useStreams,
} from "./streams"

const SAVE_GRACE_MS = 300

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export function useChatStream(
  conversationId: string | null,
  onConversation: (id: string) => void,
) {
  const queryClient = useQueryClient()
  const { streams, tokens } = useStreams()
  const key = conversationId ?? NEW_CHAT
  const stream = streams[key] ?? idle
  const viewing = useRef<string | null | undefined>(conversationId)

  useEffect(() => {
    viewing.current = conversationId
    return () => {
      viewing.current = undefined
    }
  }, [conversationId])

  const send = async (message: string, choice?: ChoiceHint) => {
    const origin = conversationId
    let at = origin ?? NEW_CHAT
    let started = false
    const abort = new AbortController()
    const update = (change: (s: Stream) => Partial<Stream>) =>
      patchStream(at, change)
    const add = (item: ActivityItem) =>
      update((s) => ({ items: [...s.items, item] }))
    update(() => ({
      ...idle,
      draft: { user: message, assistant: "" },
      choice,
      controller: abort,
    }))
    const body = {
      ...(origin ? { conversation_id: origin } : {}),
      message,
      ...(choice ? { choice } : {}),
    }
    try {
      await streamSse(
        "/api/chat",
        body,
        {
          meta: (data) => {
            const id = String((data as MetaEvent).conversation_id)
            started = true
            if (id === at) return
            moveStream(at, id)
            at = id
            void queryClient.invalidateQueries({ queryKey: conversationsKey })
            if (viewing.current === origin) onConversation(id)
          },
          status: (data) =>
            update(() => ({ status: (data as StatusEvent).text })),
          token: (data) => {
            const { text } = data as TokenEvent
            update((s) => ({
              status: null,
              draft: s.draft && {
                ...s.draft,
                assistant: s.draft.assistant + text,
              },
            }))
          },
          replace: (data) => {
            const { text } = data as ReplaceEvent
            update((s) => ({
              draft: s.draft && { ...s.draft, assistant: text },
            }))
          },
          tool_call: (data) =>
            add({ kind: "tool_call", ...(data as ToolCallEvent) }),
          tool_result: (data) =>
            add({ kind: "tool_result", ...(data as ToolResultEvent) }),
          approval_required: (data) => {
            add({ kind: "approval", ...(data as ApprovalRequiredEvent) })
            void queryClient.invalidateQueries({ queryKey: approvalsKey })
          },
          choice: (data) => add({ kind: "choice", ...(data as ChoiceEvent) }),
          google_reconnect: (data) =>
            add({ kind: "reconnect", ...(data as GoogleReconnectEvent) }),
          done: (data) => {
            const { input_tokens, output_tokens } = data as DoneEvent
            addTokens(input_tokens + output_tokens)
          },
          error: (data) =>
            update(() => ({ error: (data as ErrorEvent).message })),
        },
        abort.signal,
      )
    } catch (e) {
      if (abort.signal.aborted) await wait(SAVE_GRACE_MS)
      else
        update(() => ({
          error: e instanceof Error ? e : "Connection lost",
        }))
    }
    if (!started && !abort.signal.aborted) {
      update(() => ({ failed: true, status: null, controller: null }))
      return false
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: conversationsKey }),
      queryClient.invalidateQueries({ queryKey: approvalsKey }),
    ])
    update(() => ({ draft: null, status: null, controller: null }))
    return true
  }

  const stop = () => stream.controller?.abort()

  const retry = () =>
    stream.draft
      ? send(stream.draft.user, stream.choice)
      : Promise.resolve(true)

  const regenerate = async () => {
    if (!conversationId) return
    try {
      const { message } = await postJson<{ message: string }>(
        `/api/conversations/${conversationId}/regenerate`,
        {},
      )
      await send(message)
    } catch (e) {
      patchStream(conversationId, () => ({
        error:
          e instanceof ApiError && e.status === 409
            ? "This reply cannot be regenerated"
            : "Could not regenerate the reply",
      }))
    }
  }

  return {
    send,
    stop,
    retry,
    regenerate,
    draft: stream.failed ? null : stream.draft,
    failed: stream.failed ? (stream.draft?.user ?? null) : null,
    activity: stream.items,
    status: stream.status,
    error: stream.error,
    tokens,
    streaming: isLive(stream),
  }
}
