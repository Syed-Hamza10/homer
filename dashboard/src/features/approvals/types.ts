export type Approval = {
  id: number
  server: string
  action: string
  payload: Record<string, unknown>
  preview: string
  status: string
  channel: string
  created_at: string
  decided_at: string | null
  result: unknown
}

export type PendingApproval = Pick<Approval, "id" | "action" | "preview">

export type Decision = "approve" | "reject"
