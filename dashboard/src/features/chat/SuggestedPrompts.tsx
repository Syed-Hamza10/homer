import { suggestions } from "./suggestions"

type Props = { onPick: (message: string) => void }

export function SuggestedPrompts({ onPick }: Props) {
  return (
    <div className="grid gap-2 sm:grid-cols-2" data-testid="suggested-prompts">
      {suggestions.map((prompt) => (
        <button
          key={prompt}
          type="button"
          onClick={() => onPick(prompt)}
          className="rounded-md border border-border bg-card/80 px-3.5 py-2.5 text-left text-sm text-muted-foreground shadow-[inset_0_1px_0_var(--marble-1)] transition-colors outline-none hover:border-ring/60 hover:text-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
        >
          {prompt}
        </button>
      ))}
    </div>
  )
}
