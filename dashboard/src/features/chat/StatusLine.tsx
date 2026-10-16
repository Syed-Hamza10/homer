type Props = { tokens: number }

export function StatusLine({ tokens }: Props) {
  return (
    <p className="text-xs text-muted-foreground">
      Tokens processed locally: {tokens.toLocaleString()} · Spent on inference:
      $0.00
    </p>
  )
}
