import { useMutation, useQueryClient } from "@tanstack/react-query"
import { postJson } from "@/lib/api"
import type { Approval, ApprovalEdit } from "./types"
import { approvalsKey } from "./useApprovals"

type Args = { id: number; change: ApprovalEdit }

export function useEditApproval(onEdited: (approval: Approval) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, change }: Args) =>
      postJson<Approval>(`/api/approvals/${id}/edit`, change),
    onSuccess: async (approval) => {
      onEdited(approval)
      await queryClient.invalidateQueries({ queryKey: approvalsKey })
    },
  })
}
