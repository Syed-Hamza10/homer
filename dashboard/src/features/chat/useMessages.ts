import { useQuery } from "@tanstack/react-query"
import { getJson } from "@/lib/api"
import type { Message } from "./types"
import { conversationsKey } from "./useConversations"

export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: [...conversationsKey, conversationId, "messages"],
    queryFn: () =>
      getJson<Message[]>(`/api/conversations/${conversationId}/messages`),
    enabled: conversationId !== null,
  })
}
