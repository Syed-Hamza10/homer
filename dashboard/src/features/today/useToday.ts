import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, postJson } from "@/lib/api"
import { approvalsKey } from "@/features/approvals/useApprovals"
import type { Approval } from "@/features/approvals/types"
import type { Brief, Today } from "./types"

export const todayKey = ["today"]

export function useToday() {
  return useQuery({
    queryKey: todayKey,
    queryFn: () => getJson<Today>("/api/today"),
    refetchInterval: 10000,
  })
}

function useGenerate(url: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => postJson<Brief>(url, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: todayKey })
    },
  })
}

export function useRunBrief() {
  return useGenerate("/api/today/brief")
}

export function useRunDigest() {
  return useGenerate("/api/today/digest")
}

export function useSendFollowUp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      postJson<Approval>(`/api/followups/${id}/send`, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: todayKey })
      await queryClient.invalidateQueries({ queryKey: approvalsKey })
    },
  })
}
