export type Email = {
  message_id: string
  thread_id: string
  sender: string
  subject: string
  snippet: string
  category: string
  labels: string[]
  unread: boolean
  priority: boolean
  received_at: string
}

export type RefreshResult = {
  messages: number
  labeled: number
  failed: number
}

export type DraftResult = {
  draft_id: string | null
  to: string
  subject: string
  body: string
}

export type FollowUp = {
  id: number
  thread_id: string
  subject: string
  contact: string
  due_at: string
  status: string
  draft_id: string | null
}
