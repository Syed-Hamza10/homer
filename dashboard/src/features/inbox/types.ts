export type FolderKind = "folder" | "label" | "category"

export type Folder = {
  id: string
  name: string
  kind: FolderKind
  unread: number
  total: number
}

export type ThreadSummary = {
  id: string
  subject: string
  sender: string
  to: string
  senders: string[]
  snippet: string
  received_at: string | null
  message_count: number
  unread: boolean
  starred: boolean
  has_attachment: boolean
  labels: string[]
}

export type ThreadPage = {
  threads: ThreadSummary[]
  next_page_token: string | null
}

export type Attachment = {
  filename: string
  mime_type: string
  size: number
}

export type Message = {
  id: string
  sender: string
  to: string
  cc: string
  date: string
  received_at: string | null
  labels: string[]
  unread: boolean
  body_text: string
  body_html: string | null
  remote_images: number
  attachments: Attachment[]
}

export type Thread = {
  id: string
  subject: string
  messages: Message[]
}

export type ReplyMode = "reply" | "reply_all" | "forward"

export type ComposeDraft = {
  to: string
  subject: string
  body: string
  thread_id: string | null
}

export type LabelChange = {
  threadId: string
  add?: string[]
  remove?: string[]
}

export type RefreshResult = {
  messages: number
  labeled: number
  failed: number
}

export type FollowUp = {
  id: number
  due_at: string
}
