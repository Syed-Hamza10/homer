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

export function approvalTitle(approval: PendingApproval): string {
  const { payload } = approval
  if (approval.action === "mail_send") {
    const who = text(payload.to_name) || text(payload.to)
    return who ? `Email to ${who}` : "Email ready to send"
  }
  if (approval.action === "cal_create") {
    const title = text(payload.title)
    return title ? `New event: ${title}` : "New event"
  }
  return "Needs your approval"
}

const settledLabels: Record<string, string> = {
  rejected: "Discarded",
  expired: "Expired",
  failed: "Failed",
  unknown: "Unconfirmed",
  superseded: "Replaced",
}

export function statusLabel(action: string, status: string): string {
  if (status === "done")
    return action === "mail_send"
      ? "Sent"
      : action === "cal_create"
        ? "Created"
        : "Done"
  return settledLabels[status] ?? status
}
