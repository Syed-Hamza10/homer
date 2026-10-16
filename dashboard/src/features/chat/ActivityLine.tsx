import { ApprovalCard } from "@/features/approvals/ApprovalCard"
import type { ActivityItem } from "./types"

type Props = { item: ActivityItem }

export function ActivityLine({ item }: Props) {
  if (item.kind === "approval") {
    return (
      <div className="max-w-[75%]">
        <ApprovalCard
          approval={{
            id: item.approval_id,
            action: item.action,
            preview: item.preview,
          }}
        />
      </div>
    )
  }
  const detail =
    item.kind === "tool_call" ? JSON.stringify(item.args) : item.summary
  return (
    <p className="truncate font-mono text-xs text-muted-foreground">
      {item.kind === "tool_call" ? "→" : "←"} {item.name} {detail}
    </p>
  )
}
