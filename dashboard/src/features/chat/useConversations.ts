import { useQuery } from "@tanstack/react-query"
import { getJson } from "@/lib/api"
import type { Conversation } from "./types"

export const conversationsKey = ["conversations"]

export function useConversations() {
  return useQuery({
    queryKey: conversationsKey,
    queryFn: () => getJson<Conversation[]>("/api/conversations"),
  })
}
