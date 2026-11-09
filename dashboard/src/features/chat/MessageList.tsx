import { useEffect, useRef } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { ApprovalCard } from "@/features/approvals/ApprovalCard"
import type { Approval } from "@/features/approvals/types"
import { ActivityLine } from "./ActivityLine"
import { MessageBubble } from "./MessageBubble"
import type { ActivityItem, Message } from "./types"

type Props = {
  messages: Message[]
  approvals?: Approval[]
  loading?: boolean
  draft: { user: string; assistant: string } | null
  activity: ActivityItem[]
  status: string | null
  onRegenerate: () => void
}

type Requested = Extract<ActivityItem, { kind: "approval" }>
type Step = Exclude<ActivityItem, { kind: "approval" }>

function draftStart(messages: Message[], user: string): number {
  for (let index = messages.length - 1; index >= 0; index--) {
    const message = messages[index]
    if (message.role === "user" && message.content === user) return index
  }
  return -1
}

function byMessage(approvals: Approval[]): Map<number, Approval[]> {
  const shown = new Map<number, Approval[]>()
  for (const approval of approvals) {
    if (approval.message_id === null) continue
    shown.set(approval.message_id, [
      ...(shown.get(approval.message_id) ?? []),
      approval,
    ])
  }
  return shown
}

export function MessageList({
  messages,
  approvals = [],
  loading = false,
  draft,
  activity,
  status,
  onRegenerate,
}: Props) {
  const end = useRef<HTMLDivElement>(null)
  const start = draft ? draftStart(messages, draft.user) : -1
  const stored = draft && start >= 0 ? messages.slice(0, start + 1) : messages
  const last = stored.at(-1)
  const showDraftUser = draft && start < 0
  const placed = byMessage(approvals)
  const known = new Map(approvals.map((a) => [a.id, a]))
  const steps = activity.filter(
    (item): item is Step => item.kind !== "approval",
  )
  const live = activity.filter(
    (item): item is Requested =>
      item.kind === "approval" &&
      (draft !== null || !known.get(item.approval_id)?.message_id),
  )
  const answered = !draft && steps.length > 0 && last?.role === "assistant"
  const shown = answered ? stored.slice(0, -1) : stored
  const regenerable =
    !draft &&
    last?.role === "assistant" &&
    !last.created_approval &&
    !activity.some((item) => item.kind === "approval")

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" })
  }, [messages, approvals, draft, activity, status])

  const turn = (m: Message) => (
    <div key={m.id} className="flex flex-col gap-3">
      <MessageBubble
        role={m.role}
        content={m.content}
        createdAt={m.created_at}
        stopped={m.stopped}
        onRegenerate={regenerable && m === last ? onRegenerate : undefined}
      />
      {(placed.get(m.id) ?? []).map((approval) => (
        <ApprovalCard key={approval.id} approval={approval} />
      ))}
    </div>
  )

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="mx-auto flex max-w-2xl flex-col gap-7 px-5 pt-8 pb-6">
        {loading && (
          <div className="flex flex-col gap-4" data-testid="history-skeleton">
            <Skeleton className="h-10 w-2/5 self-end rounded-2xl" />
            <Skeleton className="h-16 w-4/5" />
            <Skeleton className="h-10 w-1/3 self-end rounded-2xl" />
            <Skeleton className="h-24 w-3/4" />
          </div>
        )}
        {shown.map(turn)}
        {showDraftUser && <MessageBubble role="user" content={draft.user} />}
        {steps.length > 0 && (
          <div className="-my-3 flex flex-col gap-1">
            {steps.map((item, index) => (
              <ActivityLine key={index} item={item} />
            ))}
          </div>
        )}
        {answered && last && turn(last)}
        {(draft || live.length > 0) && (
          <div className="flex flex-col gap-3">
            {draft && (
              <MessageBubble
                role="assistant"
                content={draft.assistant}
                status={status}
                pending
              />
            )}
            {live.map((item) => (
              <ApprovalCard
                key={item.approval_id}
                approval={{
                  id: item.approval_id,
                  action: item.action,
                  preview: item.preview,
                  payload: item.payload ?? {},
                  status: known.get(item.approval_id)?.status,
                }}
              />
            ))}
          </div>
        )}
        <div ref={end} />
      </div>
    </ScrollArea>
  )
}
