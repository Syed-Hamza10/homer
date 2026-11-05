import type { ReactNode } from "react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type Props = {
  lead?: ReactNode
  title: string
  detail?: string
  badge?: string
  highlight?: boolean
  action: { label: string; to: string; external?: boolean }
}

export function DayRow({
  lead,
  title,
  detail,
  badge,
  highlight,
  action,
}: Props) {
  return (
    <li
      className={cn(
        "flex items-center gap-3 border-t border-border/70 px-1 py-2.5",
        highlight && "rounded-md border-transparent bg-accent/50 px-2",
      )}
    >
      {lead && (
        <span className="w-14 shrink-0 text-muted-foreground tabular-nums">
          {lead}
        </span>
      )}
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="flex items-baseline gap-2">
          <span className="truncate">{title}</span>
          {badge && (
            <span className="shrink-0 text-[10px] font-medium tracking-[0.12em] text-accent-foreground uppercase">
              {badge}
            </span>
          )}
        </span>
        {detail && (
          <span className="truncate text-xs text-muted-foreground">
            {detail}
          </span>
        )}
      </span>
      <Button asChild size="xs" variant="outline" className="shrink-0">
        {action.external ? (
          <a href={action.to} target="_blank" rel="noopener noreferrer">
            {action.label}
          </a>
        ) : (
          <Link to={action.to}>{action.label}</Link>
        )}
      </Button>
    </li>
  )
}
