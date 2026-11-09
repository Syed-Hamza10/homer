import { cn } from "@/lib/utils"
import { dateKey, wallTime } from "@/lib/zoned"
import { clock } from "./format"
import { allDayOn, segmentsForDay } from "./layout"
import { dayLabel } from "./range"
import type { CalendarEvent, DateOnly } from "./types"

type Props = {
  days: DateOnly[]
  month: number
  events: CalendarEvent[]
  timeZone: string
  now: Date
  onOpen: (event: CalendarEvent) => void
  onCreateOn: (day: DateOnly) => void
  onShowDay: (day: DateOnly) => void
}

const SHOWN = 3

export function MonthGrid({
  days,
  month,
  events,
  timeZone,
  now,
  onOpen,
  onCreateOn,
  onShowDay,
}: Props) {
  const todayKey = dateKey(wallTime(now, timeZone))

  return (
    <div
      data-testid="calendar-grid"
      className="overflow-x-auto rounded-lg border border-border bg-card/60 shadow-[inset_0_1px_0_var(--marble-1)]"
    >
      <div className="grid min-w-[42rem] grid-cols-7">
        {days.slice(0, 7).map((day) => (
          <div
            key={dateKey(day)}
            className="border-b border-border bg-muted/40 px-2 py-1.5 text-[11px] text-muted-foreground"
          >
            {dayLabel(day, { weekday: "short" })}
          </div>
        ))}
        {days.map((day) => {
          const dayEvents = [
            ...allDayOn(events, day),
            ...segmentsForDay(events, day, timeZone).map((s) => s.event),
          ]
          const key = dateKey(day)
          return (
            <div
              key={key}
              data-testid={`day-${key}`}
              className={cn(
                "flex min-h-24 cursor-pointer flex-col gap-0.5 border-t border-l border-border/70 p-1 hover:bg-muted/30",
                day.month !== month && "bg-muted/20 text-muted-foreground",
              )}
              onClick={() => onCreateOn(day)}
            >
              <button
                type="button"
                className={cn(
                  "self-start rounded-sm px-1 text-xs tabular-nums hover:bg-muted",
                  key === todayKey &&
                    "bg-primary font-semibold text-primary-foreground hover:bg-primary/85",
                )}
                onClick={(e) => {
                  e.stopPropagation()
                  onShowDay(day)
                }}
              >
                {day.day}
              </button>
              {dayEvents.slice(0, SHOWN).map((event) => (
                <button
                  key={event.id}
                  type="button"
                  data-testid={`event-${event.id}`}
                  className="truncate rounded-sm bg-primary/12 px-1.5 py-0.5 text-left text-[11px] hover:bg-primary/22"
                  onClick={(e) => {
                    e.stopPropagation()
                    onOpen(event)
                  }}
                >
                  {!event.all_day && (
                    <span className="mr-1 text-muted-foreground tabular-nums">
                      {clock(event.start, timeZone)}
                    </span>
                  )}
                  {event.title || "(no title)"}
                </button>
              ))}
              {dayEvents.length > SHOWN && (
                <button
                  type="button"
                  className="self-start px-1 text-[10px] text-muted-foreground hover:text-foreground"
                  onClick={(e) => {
                    e.stopPropagation()
                    onShowDay(day)
                  }}
                >
                  {dayEvents.length - SHOWN} more
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
