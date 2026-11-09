import type { GoogleStatus } from "@/features/settings/types"

export type Brief = { kind: string; day: string; content: string }

export type Reminder = {
  id: number
  text: string
  due_at: string
  status: string
  created_at: string
}

export type Event = {
  event_id: string
  title: string
  start: string
  end: string
  location: string
  attendees: string[]
}

export type FollowUp = {
  id: number
  thread_id: string
  subject: string
  contact: string
  due_at: string
  status: string
  draft_id: string | null
  draft_preview: string | null
}

export type ModelStatus = "running" | "stopped" | "missing"

export type Health = {
  ollama: "ok" | "down"
  model_pulled: "ok" | "down"
  model_status: ModelStatus
  servers: Record<string, "ok" | "down">
  self_email: "off" | "ok" | "mismatch" | "unknown"
  checked_at: string
}

export type Today = {
  day: string
  brief: Brief | null
  digest: Brief | null
  events: Event[]
  reminders: Reminder[]
  follow_ups: FollowUp[]
  unread: number
  pending_approvals: number
  health: Health | null
  google: GoogleStatus
  card: DayCardData
}

export type Meeting = {
  event_id: string
  title: string
  start: string
  end: string
  attendees: string[]
  join_url: string | null
}

export type EmailNeed = {
  message_id: string
  thread_id: string
  sender: string
  subject: string
  received_at: string
  reason: string
}

export type FollowUpDue = {
  id: number
  thread_id: string
  subject: string
  contact: string
  due_at: string
}

export type ApprovalWaiting = { id: number; action: string; preview: string }

export type DayCardData = {
  greeting: string
  meetings: Meeting[]
  next_event_id: string | null
  emails: EmailNeed[]
  follow_ups: FollowUpDue[]
  approvals: ApprovalWaiting[]
}
