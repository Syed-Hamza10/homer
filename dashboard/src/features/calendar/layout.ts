import { dateKey, instantOf, wallTime } from "@/lib/zoned"
import type { CalendarEvent, DateOnly } from "./types"

const DAY_MINUTES = 1440
const MIN_LENGTH = 15

export type Segment = { event: CalendarEvent; top: number; bottom: number }

export type Placed = Segment & { column: number; columns: number }

export function segmentsForDay(
  events: CalendarEvent[],
  day: DateOnly,
  timeZone: string,
): Segment[] {
  const opens = instantOf({ ...day, hour: 0, minute: 0 }, timeZone).getTime()
  const closes = opens + DAY_MINUTES * 60000
  const segments: Segment[] = []
  for (const event of events) {
    if (event.all_day) continue
    const start = new Date(event.start).getTime()
    const end = new Date(event.end).getTime()
    if (end <= opens || start >= closes) continue
    const startWall = wallTime(new Date(start), timeZone)
    const endWall = wallTime(new Date(end), timeZone)
    const top = start <= opens ? 0 : startWall.hour * 60 + startWall.minute
    const bottom =
      end >= closes ? DAY_MINUTES : endWall.hour * 60 + endWall.minute
    segments.push({
      event,
      top,
      bottom: Math.min(DAY_MINUTES, Math.max(bottom, top + MIN_LENGTH)),
    })
  }
  return segments
}

export function placeSegments(segments: Segment[]): Placed[] {
  const ordered = [...segments].sort(
    (a, b) => a.top - b.top || b.bottom - a.bottom,
  )
  const placed: Placed[] = []
  let cluster: Placed[] = []
  let clusterEnd = -1
  const close = () => {
    const columns = Math.max(1, ...cluster.map((item) => item.column + 1))
    for (const item of cluster) item.columns = columns
    cluster = []
  }
  for (const segment of ordered) {
    if (segment.top >= clusterEnd) {
      close()
      clusterEnd = -1
    }
    const taken = new Set(
      cluster
        .filter((item) => item.bottom > segment.top)
        .map((item) => item.column),
    )
    let column = 0
    while (taken.has(column)) column += 1
    const item = { ...segment, column, columns: 1 }
    cluster.push(item)
    placed.push(item)
    clusterEnd = Math.max(clusterEnd, segment.bottom)
  }
  close()
  return placed
}

export function allDayOn(
  events: CalendarEvent[],
  day: DateOnly,
): CalendarEvent[] {
  const key = dateKey(day)
  return events.filter((event) => {
    const first = event.start.slice(0, 10)
    const end = event.end.slice(0, 10)
    return event.all_day && (key === first || (key > first && key < end))
  })
}
