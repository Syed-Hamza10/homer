import { addDays, dateKey, formatIn, parseWall } from "@/lib/zoned"
import { dayLabel } from "./range"
import type { CalendarEvent } from "./types"

export function clock(value: string | Date, timeZone: string): string {
  return formatIn(new Date(value), timeZone, {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  })
}

function shortDay(value: Date, timeZone: string): string {
  return formatIn(value, timeZone, {
    weekday: "short",
    day: "numeric",
    month: "short",
  })
}

export function whenText(event: CalendarEvent, timeZone: string): string {
  if (event.all_day) {
    const first = parseWall(event.start)
    const last = addDays(parseWall(event.end || event.start), -1)
    const options = {
      weekday: "short",
      day: "numeric",
      month: "short",
    } as const
    if (dateKey(last) <= dateKey(first))
      return `All day · ${dayLabel(first, options)}`
    return `All day · ${dayLabel(first, options)} – ${dayLabel(last, options)}`
  }
  const start = new Date(event.start)
  const end = new Date(event.end)
  const sameDay = shortDay(start, timeZone) === shortDay(end, timeZone)
  const tail = sameDay
    ? clock(end, timeZone)
    : `${shortDay(end, timeZone)} ${clock(end, timeZone)}`
  return `${shortDay(start, timeZone)} · ${clock(start, timeZone)}–${tail}`
}

const RESPONSES: Record<string, string> = {
  accepted: "Accepted",
  declined: "Declined",
  tentative: "Maybe",
  needsAction: "No reply",
}

export function responseText(response: string): string {
  return RESPONSES[response] ?? response
}
