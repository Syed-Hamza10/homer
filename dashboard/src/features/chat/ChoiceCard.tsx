import { Check } from "lucide-react"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { shortcutName } from "@/lib/shortcuts"
import { cn } from "@/lib/utils"
import type { ChoiceEvent, ChoiceOption } from "./types"

type Props = {
  card: ChoiceEvent
  active: boolean
  onPick: (option: ChoiceOption) => void
  onOther: () => void
}

const KEYS = 9

export function ChoiceCard({ card, active, onPick, onOther }: Props) {
  const [picked, setPicked] = useState<string | null>(null)
  const answered = picked ?? card.answered ?? null
  const open = active && answered === null

  const pick = (option: ChoiceOption) => {
    if (!open) return
    setPicked(option.id)
    onPick(option)
  }

  useEffect(() => {
    if (!open) return
    const listener = (event: KeyboardEvent) => {
      const name = shortcutName(event)
      const option =
        name && /^[1-9]$/.test(name) && card.options[Number(name) - 1]
      if (!option) return
      event.preventDefault()
      setPicked(option.id)
      onPick(option)
    }
    window.addEventListener("keydown", listener)
    return () => window.removeEventListener("keydown", listener)
  }, [open, card.options, onPick])

  return (
    <section
      aria-label={card.prompt}
      data-testid={`choice-${card.question_id}`}
      className="animate-enter overflow-hidden rounded-xl border border-border bg-card text-card-foreground shadow-[0_1px_2px_oklch(0_0_0/0.04),inset_0_1px_0_var(--marble-1)]"
    >
      <ul className="divide-y divide-border/80">
        {card.options.map((option, index) => {
          const chosen = answered === option.id
          return (
            <li key={option.id}>
              <button
                type="button"
                disabled={!open}
                aria-pressed={chosen}
                onClick={() => pick(option)}
                className={cn(
                  "flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors enabled:hover:bg-muted/60 disabled:cursor-default",
                  !open && !chosen && "opacity-55",
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    "flex size-6 shrink-0 items-center justify-center rounded-md border border-border text-xs text-muted-foreground tabular-nums",
                    chosen && "border-brand/30 bg-brand/10 text-foreground",
                  )}
                >
                  {chosen ? (
                    <Check className="size-3.5" strokeWidth={2} />
                  ) : (
                    index < KEYS && index + 1
                  )}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium">
                    {option.label}
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    {option.detail}
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      {card.allow_other && open && (
        <footer className="border-t border-border/80 bg-muted/40 px-2 py-1.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={onOther}
            className="text-muted-foreground"
          >
            Someone else…
          </Button>
        </footer>
      )}
    </section>
  )
}
