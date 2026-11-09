import { useEffect, useRef, useState, type PointerEvent } from "react"
import { cn } from "@/lib/utils"
import { dateKey, wallTime, type WallTime } from "@/lib/zoned"
import { EventBlock } from "./EventBlock"
import { shiftedInstant } from "./formValue"
import {
  DAY_MINUTES,
  HOUR_PX,
  SNAP_MINUTES,
  minuteAt,
  pixels,
  snap,
  wallAt,
} from "./grid"
import { allDayOn, placeSegments, segmentsForDay } from "./layout"
import { dayLabel } from "./range"
import type { CalendarEvent, DateOnly } from "./types"

type Props = {
  days: DateOnly[]
  events: CalendarEvent[]
  timeZone: string
  now: Date
  onOpen: (event: CalendarEvent) => void
  onCreate: (start: WallTime, end: WallTime) => void
  onMove: (event: CalendarEvent, start: Date, end: Date) => void
}

type Selection = { day: number; from: number; to: number }

type Drag = {
  event: CalendarEvent
  x: number
  y: number
  columnWidth: number
  dx: number
  dy: number
  moved: boolean
}

const HOURS = Array.from({ length: 24 }, (_, hour) => hour)
const DEFAULT_MINUTES = 30
const DRAG_THRESHOLD = 4

export function TimeGrid({
  days,
  events,
  timeZone,
  now,
  onOpen,
  onCreate,
  onMove,
}: Props) {
  const scroller = useRef<HTMLDivElement>(null)
  const columnsRef = useRef<HTMLDivElement>(null)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [drag, setDrag] = useState<Drag | null>(null)
  const nowWall = wallTime(now, timeZone)
  const todayKey = dateKey(nowWall)
  const template = `3.5rem repeat(${days.length}, minmax(${days.length > 1 ? "7rem" : "12rem"}, 1fr))`

  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = 7 * HOUR_PX
  }, [])

  const startSelection = (e: PointerEvent<HTMLDivElement>, day: number) => {
    if (e.button !== 0) return
    const minute = minuteAt(
      e.clientY,
      e.currentTarget.getBoundingClientRect().top,
    )
    e.currentTarget.setPointerCapture?.(e.pointerId)
    setSelection({ day, from: minute, to: minute })
  }

  const extendSelection = (e: PointerEvent<HTMLDivElement>, day: number) => {
    if (!selection || selection.day !== day) return
    const minute = minuteAt(
      e.clientY,
      e.currentTarget.getBoundingClientRect().top,
    )
    setSelection({ ...selection, to: minute })
  }

  const finishSelection = () => {
    if (!selection) return
    let from = Math.min(selection.from, selection.to)
    let to = Math.max(selection.from, selection.to)
    if (to - from < SNAP_MINUTES) {
      from = Math.min(from, DAY_MINUTES - DEFAULT_MINUTES)
      to = from + DEFAULT_MINUTES
    }
    const day = days[selection.day]
    setSelection(null)
    onCreate(wallAt(day, from), wallAt(day, to))
  }

  const startDrag = (e: PointerEvent<HTMLDivElement>, event: CalendarEvent) => {
    e.stopPropagation()
    if (e.button !== 0) return
    e.currentTarget.setPointerCapture?.(e.pointerId)
    const width = columnsRef.current?.getBoundingClientRect().width ?? 0
    setDrag({
      event,
      x: e.clientX,
      y: e.clientY,
      columnWidth: width / days.length,
      dx: 0,
      dy: 0,
      moved: false,
    })
  }

  const moveDrag = (e: PointerEvent<HTMLDivElement>) => {
    if (!drag) return
    const dx = e.clientX - drag.x
    const dy = e.clientY - drag.y
    const moved =
      drag.moved ||
      Math.abs(dx) > DRAG_THRESHOLD ||
      Math.abs(dy) > DRAG_THRESHOLD
    setDrag({ ...drag, dx, dy, moved })
  }

  const shiftOf = (current: Drag) => ({
    days: current.columnWidth
      ? Math.round(current.dx / current.columnWidth)
      : 0,
    minutes: snap((current.dy / HOUR_PX) * 60),
  })

  const endDrag = (e: PointerEvent<HTMLDivElement>) => {
    e.stopPropagation()
    if (!drag) return
    const current = drag
    setDrag(null)
    if (!current.moved) {
      onOpen(current.event)
      return
    }
    const shift = shiftOf(current)
    if (!shift.days && !shift.minutes) return
    const start = new Date(current.event.start)
    const length = new Date(current.event.end).getTime() - start.getTime()
    const moved = shiftedInstant(start, shift.days, shift.minutes, timeZone)
    onMove(current.event, moved, new Date(moved.getTime() + length))
  }

  const offsetFor = (event: CalendarEvent) => {
    if (!drag || drag.event.id !== event.id || !drag.moved) return null
    const shift = shiftOf(drag)
    return { x: shift.days * drag.columnWidth, y: pixels(shift.minutes) }
  }

  return (
    <div
      ref={scroller}
      data-testid="calendar-grid"
      className="h-[68vh] min-h-96 overflow-auto rounded-lg border border-border bg-card/60 shadow-[inset_0_1px_0_var(--marble-1)]"
    >
      <div className="sticky top-0 z-30 border-b border-border bg-card">
        <div className="grid" style={{ gridTemplateColumns: template }}>
          <div />
          {days.map((day) => {
            const today = dateKey(day) === todayKey
            return (
              <div
                key={dateKey(day)}
                className={cn(
                  "border-l border-border/70 px-2 py-1.5 text-xs text-muted-foreground",
                  today && "font-semibold text-foreground",
                )}
              >
                {dayLabel(day, { weekday: "short", day: "numeric" })}
              </div>
            )
          })}
        </div>
        <div
          className="grid border-t border-border/70"
          style={{ gridTemplateColumns: template }}
        >
          <div className="px-1 py-1 text-right text-[11px] text-muted-foreground">
            All day
          </div>
          {days.map((day) => (
            <div
              key={dateKey(day)}
              className="flex min-h-6 flex-col gap-0.5 border-l border-border/70 p-0.5"
            >
              {allDayOn(events, day).map((event) => (
                <button
                  key={event.id}
                  type="button"
                  data-testid={`event-${event.id}`}
                  className="truncate rounded-sm bg-primary/15 px-1.5 py-0.5 text-left text-[11px] hover:bg-primary/25"
                  onClick={() => onOpen(event)}
                >
                  {event.title || "(no title)"}
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="grid" style={{ gridTemplateColumns: template }}>
        <div className="relative" style={{ height: pixels(DAY_MINUTES) }}>
          {HOURS.slice(1).map((hour) => (
            <span
              key={hour}
              className="absolute right-1.5 -translate-y-1/2 text-[10px] text-muted-foreground tabular-nums"
              style={{ top: hour * HOUR_PX }}
            >
              {String(hour).padStart(2, "0")}:00
            </span>
          ))}
        </div>
        <div
          ref={columnsRef}
          className="relative grid"
          style={{
            gridColumn: "2 / -1",
            gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))`,
          }}
        >
          {days.map((day, index) => {
            const placed = placeSegments(segmentsForDay(events, day, timeZone))
            const today = dateKey(day) === todayKey
            const picking = selection?.day === index ? selection : null
            return (
              <div
                key={dateKey(day)}
                data-testid={`day-${dateKey(day)}`}
                className="relative border-l border-border/70"
                style={{
                  height: pixels(DAY_MINUTES),
                  backgroundImage: `repeating-linear-gradient(to bottom, var(--border) 0, var(--border) 1px, transparent 1px, transparent ${HOUR_PX}px)`,
                }}
                onPointerDown={(e) => startSelection(e, index)}
                onPointerMove={(e) => extendSelection(e, index)}
                onPointerUp={finishSelection}
              >
                {picking && (
                  <div
                    className="absolute inset-x-0.5 rounded-sm border border-ring/60 bg-ring/15"
                    style={{
                      top: pixels(Math.min(picking.from, picking.to)),
                      height: Math.max(
                        pixels(Math.abs(picking.to - picking.from)),
                        pixels(SNAP_MINUTES),
                      ),
                    }}
                  />
                )}
                {placed.map((item) => (
                  <EventBlock
                    key={`${item.event.id}-${item.top}`}
                    placed={item}
                    timeZone={timeZone}
                    offset={offsetFor(item.event)}
                    onPointerDown={(e) => startDrag(e, item.event)}
                    onPointerMove={moveDrag}
                    onPointerUp={endDrag}
                    onOpen={() => onOpen(item.event)}
                  />
                ))}
                {today && (
                  <div
                    aria-hidden
                    data-testid="now-line"
                    className="pointer-events-none absolute inset-x-0 z-10 h-px bg-destructive"
                    style={{ top: pixels(nowWall.hour * 60 + nowWall.minute) }}
                  >
                    <span className="absolute -top-1 -left-1 size-2 rounded-full bg-destructive" />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
