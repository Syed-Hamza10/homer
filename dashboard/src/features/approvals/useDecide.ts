import { useMutation, useQueryClient } from "@tanstack/react-query"
import { ApiError, postJson } from "@/lib/api"
import type { Approval, Decision } from "./types"
import { approvalsKey } from "./useApprovals"

type Args = { id: number; decision: Decision }

export function describeDecisionError(error: Error | null): string | null {
  if (!error) return null
  if (error instanceof ApiError && error.status === 409)
    return "Already decided"
  if (error instanceof ApiError) return `Request failed (${error.status})`
  return "Cannot reach the Homer server"
}

export function useDecide(onDecided?: (approval: Approval) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision }: Args) =>
      postJson<Approval>(`/api/approvals/${id}/${decision}`, {}),
    onSuccess: async (approval) => {
      onDecided?.(approval)
      await queryClient.invalidateQueries({ queryKey: approvalsKey })
    },
  })
}
