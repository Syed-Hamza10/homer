import type { ReactNode } from "react"

type Props = {
  eyebrow: string
  title: string
  description?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ eyebrow, title, description, actions }: Props) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4 border-b border-border pb-5">
      <div className="flex min-w-0 flex-col gap-2">
        <p className="flex items-center gap-2 text-[9px] font-medium tracking-[0.32em] uppercase text-muted-foreground">
          <span
            aria-hidden
            className="size-1 rotate-45 border border-ring/70"
          />
          {eyebrow}
        </p>
        <h1 className="font-heading text-3xl leading-none tracking-tight">
          {title}
        </h1>
        {description && (
          <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2 pb-0.5">{actions}</div>
      )}
    </header>
  )
}
