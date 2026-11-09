type Props = { tokens: number }

export function StatusLine({ tokens }: Props) {
  return (
    <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 px-2 text-[11px] text-muted-foreground/90">
      <span className="hidden sm:inline">
        Enter to send, Shift+Enter for a new line
      </span>
      <span>
        Tokens processed locally: {tokens.toLocaleString()} · Spent on
        inference: $0.00
      </span>
    </div>
  )
}
