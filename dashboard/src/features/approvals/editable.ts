import type { EventEdit, MailEdit, PendingApproval } from "./types"

const text = (value: unknown): string =>
  typeof value === "string" ? value : ""

export function mailFields(approval: PendingApproval): MailEdit | null {
  const { payload } = approval
  if (approval.action !== "mail_send" || typeof payload.to !== "string")
    return null
  return {
    to: payload.to,
    subject: text(payload.subject),
    body: text(payload.body),
  }
}

export function eventFields(approval: PendingApproval): EventEdit | null {
  const { payload } = approval
  const start = text(payload.start)
  const end = text(payload.end)
  if (approval.action !== "cal_create" || !start.includes("T")) return null
  return {
    title: text(payload.title),
    date: start.slice(0, 10),
    start: start.slice(11, 16),
    end: end.slice(11, 16),
    attendees: Array.isArray(payload.attendees)
      ? payload.attendees.map(String)
      : [],
  }
}

export function primaryLabel(action: string): string {
  if (action === "mail_send") return "Send"
  if (action === "cal_create") return "Create"
  return "Approve"
}
