import type { Source } from "./sources"

type Props = { sources: Source[] }

export function SourceChips({ sources }: Props) {
  return (
    <ul className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Sources">
      {sources.map((source) => (
        <li key={source.url}>
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            title={source.url}
            className="flex max-w-56 items-baseline gap-1.5 rounded-full border border-border bg-background/60 px-2.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-ring/60 hover:text-foreground"
          >
            <span className="shrink-0 font-medium text-foreground/80">
              {source.domain}
            </span>
            {source.title !== source.domain && (
              <span className="truncate">{source.title}</span>
            )}
          </a>
        </li>
      ))}
    </ul>
  )
}
