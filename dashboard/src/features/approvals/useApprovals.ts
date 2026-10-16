import { useQuery } from "@tanstack/react-query"
import { getJson } from "@/lib/api"
import type { Approval } from "./types"

export const approvalsKey = ["approvals"]

export function useApprovals() {
  return useQuery({
    queryKey: approvalsKey,
    queryFn: () => getJson<Approval[]>("/api/approvals?status=pending"),
    refetchInterval: 5000,
  })
}
