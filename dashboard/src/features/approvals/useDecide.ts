import { useMutation, useQueryClient } from "@tanstack/react-query"
import { postJson } from "@/lib/api"
import { eventsKey } from "@/features/calendar/useCalendar"
import { mailKey } from "@/features/inbox/useMail"
import { todayKey } from "@/features/today/useToday"
import type { Approval, Decision } from "./types"
import { approvalsKey } from "./useApprovals"

type Args = { id: number; decision: Decision }

const ran = new Set(["done", "unknown"])

export function useDecide(onDecided?: (approval: Approval) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision }: Args) =>
      postJson<Approval>(`/api/approvals/${id}/${decision}`, {}),
    onSuccess: async (approval) => {
      onDecided?.(approval)
      const keys = ran.has(approval.status)
        ? [approvalsKey, eventsKey, mailKey, todayKey]
        : [approvalsKey]
      await Promise.all(
        keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
      )
    },
  })
}
