import type { Conversation } from "./types"

export type ConversationGroup = { label: string; items: Conversation[] }

const LABELS = ["Today", "Yesterday", "Previous 7 days", "Older"] as const
const DAY = 86_400_000

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

function labelFor(updated: Date, now: Date): (typeof LABELS)[number] {
  const days = Math.round((startOfDay(now) - startOfDay(updated)) / DAY)
  if (days <= 0) return "Today"
  if (days === 1) return "Yesterday"
  if (days <= 7) return "Previous 7 days"
  return "Older"
}

export function filterConversations(
  conversations: Conversation[],
  query: string,
): Conversation[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return conversations
  return conversations.filter((c) =>
    (c.title || "Untitled").toLowerCase().includes(needle),
  )
}

export function groupConversations(
  conversations: Conversation[],
  now: Date = new Date(),
): ConversationGroup[] {
  const buckets = new Map<string, Conversation[]>(LABELS.map((l) => [l, []]))
  for (const c of conversations)
    buckets.get(labelFor(new Date(c.updated_at), now))?.push(c)
  return LABELS.map((label) => ({
    label,
    items: buckets.get(label) ?? [],
  })).filter((group) => group.items.length > 0)
}
