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
  conversation_id: number | null
  message_id: number | null
}

export type PendingApproval = Pick<
  Approval,
  "id" | "action" | "preview" | "payload"
> &
  Partial<Pick<Approval, "status" | "result">>

export type Decision = "approve" | "reject"

export type MailEdit = { to: string; subject: string; body: string }

export type EventEdit = {
  title: string
  date: string
  start: string
  end: string
  attendees: string[]
}

export type ApprovalEdit = MailEdit | EventEdit
