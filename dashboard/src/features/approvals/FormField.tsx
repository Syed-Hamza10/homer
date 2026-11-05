import type { ReactNode } from "react"

type Props = { label: string; children: ReactNode }

export function FormField({ label, children }: Props) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      {label}
      {children}
    </label>
  )
}
