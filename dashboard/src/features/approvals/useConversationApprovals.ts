import { useQuery } from "@tanstack/react-query"
import { getJson } from "@/lib/api"
import type { Approval } from "./types"
import { approvalsKey } from "./useApprovals"

export function useConversationApprovals(conversationId: string | null) {
  return useQuery({
    queryKey: [...approvalsKey, "conversation", conversationId],
    queryFn: () =>
      getJson<Approval[]>(`/api/approvals?conversation_id=${conversationId}`),
    enabled: conversationId !== null,
  })
}
