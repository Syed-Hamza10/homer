import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import type { ActivityItem } from "./types"

type Props = { item: Exclude<ActivityItem, { kind: "approval" }> }

export function ActivityLine({ item }: Props) {
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
    <p className="truncate font-mono text-[11px] text-muted-foreground/70">
      {item.kind === "tool_call" ? "→" : "←"} {item.name} {detail}
    </p>
  )
}
