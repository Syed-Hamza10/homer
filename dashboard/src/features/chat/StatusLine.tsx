type Props = { tokens: number }

export function StatusLine({ tokens }: Props) {
  return (
    <p className="text-[10px] font-medium tracking-[0.14em] uppercase text-muted-foreground">
      Tokens processed locally: {tokens.toLocaleString()} · Spent on inference:
      $0.00
    </p>
  )
}
