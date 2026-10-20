import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, postJson } from "@/lib/api"
import { todayKey } from "@/features/today/useToday"
import type { DraftResult, Email, FollowUp, RefreshResult } from "./types"

export const inboxKey = ["inbox"]

function useInboxMutation<T>(url: string, body: unknown) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => postJson<T>(url, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: inboxKey })
      await queryClient.invalidateQueries({ queryKey: todayKey })
    },
  })
}

export function useInbox() {
  return useQuery({
    queryKey: inboxKey,
    queryFn: () => getJson<Email[]>("/api/inbox"),
    refetchInterval: 10000,
  })
}

export function useRefreshInbox() {
  return useInboxMutation<RefreshResult>("/api/inbox/refresh", {})
}

export function useArchive(messageId: string) {
  return useInboxMutation<Email>(`/api/inbox/${messageId}/archive`, {})
}

export function useFollowUp(messageId: string, days = 3) {
  return useInboxMutation<FollowUp>(`/api/inbox/${messageId}/follow-up`, {
    days,
  })
}

export function useDraft(messageId: string) {
  return useInboxMutation<DraftResult>(`/api/inbox/${messageId}/draft`, {})
}
