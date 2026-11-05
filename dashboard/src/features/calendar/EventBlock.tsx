import type { PointerEvent } from "react"
import { cn } from "@/lib/utils"
import { clock } from "./format"
import { pixels } from "./grid"
import type { Placed } from "./layout"

type Props = {
  placed: Placed
  timeZone: string
  offset: { x: number; y: number } | null
  onPointerDown: (event: PointerEvent<HTMLDivElement>) => void
  onPointerMove: (event: PointerEvent<HTMLDivElement>) => void
  onPointerUp: (event: PointerEvent<HTMLDivElement>) => void
  onOpen: () => void
}

export function EventBlock({
  placed,
  timeZone,
  offset,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onOpen,
}: Props) {
  const { event, top, bottom, column, columns } = placed
  const width = 100 / columns
  const short = bottom - top < 45

  return (
    <div
      role="button"
      tabIndex={0}
      data-testid={`event-${event.id}`}
      aria-label={`${event.title || "(no title)"}, ${clock(event.start, timeZone)}`}
      className={cn(
        "absolute cursor-grab touch-none overflow-hidden rounded-sm border border-primary/30 bg-primary/12 px-1.5 py-0.5 text-left text-[11px] leading-tight shadow-[inset_2px_0_0_var(--primary)] select-none hover:bg-primary/18 focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:outline-none",
        offset && "z-20 cursor-grabbing opacity-80",
      )}
      style={{
        top: pixels(top),
        height: Math.max(pixels(bottom - top) - 1, 14),
        left: `calc(${column * width}% + 1px)`,
        width: `calc(${width}% - 2px)`,
        transform: offset
          ? `translate(${offset.x}px, ${offset.y}px)`
          : undefined,
      }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onOpen()
        }
      }}
    >
      <p className="truncate font-medium">{event.title || "(no title)"}</p>
      {!short && (
        <p className="truncate text-muted-foreground tabular-nums">
          {clock(event.start, timeZone)}–{clock(event.end, timeZone)}
        </p>
      )}
    </div>
  )
}
