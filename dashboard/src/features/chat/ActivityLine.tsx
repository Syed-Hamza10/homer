import { ChevronRight, LoaderCircle } from "lucide-react"
import { useStoredFlag } from "@/lib/useStoredFlag"
import { cn } from "@/lib/utils"
import { headline, stepRow, type ToolStep } from "./activity"

export const ACTIVITY_OPEN_KEY = "homer.chat.activity.open"

type Props = {
  steps: ToolStep[]
  running: boolean
  status: string | null
  sources: number
}

export function ActivityLine({ steps, running, status, sources }: Props) {
  const [open, setOpen] = useStoredFlag(ACTIVITY_OPEN_KEY)
  const expandable = steps.length > 0
  return (
    <div className="text-xs text-muted-foreground" data-testid="activity">
      <button
        type="button"
        aria-expanded={expandable ? open : undefined}
        disabled={!expandable}
        onClick={() => setOpen(!open)}
        className="flex max-w-full items-center gap-1.5 text-left transition-colors enabled:hover:text-foreground"
      >
        {running ? (
          <LoaderCircle aria-hidden className="size-3 shrink-0 animate-spin" />
        ) : (
          <ChevronRight
            aria-hidden
            className={cn(
              "size-3 shrink-0 transition-transform",
              open && "rotate-90",
            )}
          />
        )}
        <span aria-live="polite" className="truncate">
          {headline(steps, { running, status, sources })}
        </span>
      </button>
      {open && expandable && (
        <ul
          aria-label="Tool activity"
          className="mt-1.5 ml-1.5 flex flex-col gap-1 border-l border-border pl-3"
        >
          {steps.map((step, index) => {
            const row = stepRow(step, running)
            return (
              <li
                key={index}
                className={cn(
                  "flex min-w-0 gap-1.5",
                  row.failed && "text-destructive/80",
                )}
              >
                <span className="shrink-0">{row.text}</span>
                {row.detail && (
                  <span className="truncate text-muted-foreground/70">
                    {row.detail}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
