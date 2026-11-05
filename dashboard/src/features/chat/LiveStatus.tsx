type Props = { text: string | null }

export function LiveStatus({ text }: Props) {
  return (
    <div className="flex items-center gap-2 text-muted-foreground">
      <span
        aria-hidden
        className="typing-dots flex items-center gap-1"
        data-testid="typing-indicator"
      >
        <span />
        <span />
        <span />
      </span>
      <p role="status" className="text-xs tracking-[0.02em]">
        {text ?? "Thinking…"}
      </p>
    </div>
  )
}
