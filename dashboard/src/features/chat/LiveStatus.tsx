type Props = { text: string | null }

export function LiveStatus({ text }: Props) {
  return (
    <p
      role="status"
      className="animate-pulse text-xs tracking-[0.02em] text-muted-foreground"
    >
      {text ?? "Thinking…"}
    </p>
  )
}
