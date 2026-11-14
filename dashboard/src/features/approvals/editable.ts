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

const timed = (
  start: string,
  end: string,
  title: string,
  attendees: string[],
): EventEdit | null =>
  start.includes("T")
    ? {
        title,
        date: start.slice(0, 10),
        start: start.slice(11, 16),
        end_date: end.slice(0, 10) || start.slice(0, 10),
        end: end.slice(11, 16),
        attendees,
      }
    : null

const quotedTitle = (preview: string): string =>
  /'(.+?)'/.exec(preview)?.[1] ?? ""

export function eventFields(approval: PendingApproval): EventEdit | null {
  const { payload } = approval
  if (approval.action === "cal_update") {
    const changes = (payload.changes ?? {}) as Record<string, unknown>
    return timed(
      text(changes.start),
      text(changes.end),
      text(changes.title) || quotedTitle(approval.preview),
      [],
    )
  }
  if (approval.action !== "cal_create") return null
  return timed(
    text(payload.start),
    text(payload.end),
    text(payload.title),
    Array.isArray(payload.attendees) ? payload.attendees.map(String) : [],
  )
}

export function followedEndDate(
  startDate: string,
  endDate: string,
  nextStart: string,
): string {
  return endDate === startDate || endDate < nextStart ? nextStart : endDate
}

export function eventOrderProblem(value: EventEdit): string | null {
  return `${value.end_date}T${value.end}` <= `${value.date}T${value.start}`
    ? "The end must be after the start."
    : null
}

export const editsGuests = (action: string): boolean => action !== "cal_update"

export function primaryLabel(action: string): string {
  if (action === "mail_send") return "Send email"
  if (action === "cal_create") return "Create event"
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
