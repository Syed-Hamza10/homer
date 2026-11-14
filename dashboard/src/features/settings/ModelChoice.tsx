import { cn } from "@/lib/utils"
import { tierLabels, tierNotes } from "./tiers"
import type { ModelTier } from "./types"

type Props = {
  tiers: ModelTier[]
  value: string
  onChange: (value: string) => void
}

export function ModelChoice({ tiers, value, onChange }: Props) {
  const choices = [
    { id: "", label: "Automatic", note: "Homer picks what fits this computer" },
    ...tiers.map((tier) => ({
      id: tier,
      label: tierLabels[tier],
      note: tierNotes[tier],
    })),
  ]
  return (
    <div role="radiogroup" aria-label="AI model" className="grid gap-2">
      {choices.map((choice) => (
        <label
          key={choice.id}
          className={cn(
            "flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2 text-sm",
            value === choice.id
              ? "border-ring/60 bg-muted/50"
              : "border-border",
          )}
        >
          <input
            type="radio"
            name="model-tier"
            className="mt-1"
            value={choice.id}
            checked={value === choice.id}
            onChange={() => onChange(choice.id)}
          />
          <span className="flex flex-col">
            <span className="font-medium">{choice.label}</span>
            <span className="text-xs text-muted-foreground">{choice.note}</span>
          </span>
        </label>
      ))}
    </div>
  )
}
