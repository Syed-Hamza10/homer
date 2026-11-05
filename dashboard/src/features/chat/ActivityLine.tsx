import { Link } from "react-router"
import { Button } from "@/components/ui/button"
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
            payload: item.payload ?? {},
          }}
        />
      </div>
    )
  }
  if (item.kind === "reconnect") {
    return (
      <Button asChild variant="outline" size="sm" className="self-start">
        <Link to={item.url}>Reconnect Google</Link>
      </Button>
    )
  }
  const detail =
    item.kind === "tool_call" ? JSON.stringify(item.args) : item.summary
  return (
    <p className="truncate font-mono text-[11px] text-muted-foreground/80">
      {item.kind === "tool_call" ? "→" : "←"} {item.name} {detail}
    </p>
  )
}
