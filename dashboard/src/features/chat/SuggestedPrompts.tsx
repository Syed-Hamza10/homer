import { suggestions } from "./suggestions"

type Props = { onPick: (message: string) => void }

export function SuggestedPrompts({ onPick }: Props) {
  return (
    <div
      className="flex flex-wrap justify-center gap-2"
      data-testid="suggested-prompts"
    >
      {suggestions.map((prompt) => (
        <button
          key={prompt}
          type="button"
          onClick={() => onPick(prompt)}
          className="rounded-full border border-border bg-card/70 px-3.5 py-1.5 text-[13px] text-muted-foreground transition-colors outline-none hover:border-ring/50 hover:text-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
        >
          {prompt}
        </button>
      ))}
    </div>
  )
}
