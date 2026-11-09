import { Landmark } from "lucide-react"
import { cn } from "@/lib/utils"

type Props = { compact?: boolean }

export function Wordmark({ compact = false }: Props) {
  return (
    <span className="flex items-center gap-2.5">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-sidebar-border bg-card text-sidebar-primary shadow-[inset_0_1px_0_var(--marble-1)]">
        <Landmark aria-hidden className="size-4" strokeWidth={1.5} />
      </span>
      <span
        className={cn(
          "font-heading text-lg tracking-[0.16em] uppercase",
          compact && "sr-only",
        )}
      >
        Homer
      </span>
    </span>
  )
}
