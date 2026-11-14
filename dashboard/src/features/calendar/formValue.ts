import { followedEndDate } from "@/features/approvals/editable"
import { addDays, instantOf, wallString, wallTime } from "@/lib/zoned"
import type { WallTime } from "@/lib/zoned"
import type { CalendarEvent, EventFields, FormValue } from "./types"

export const emptyForm: FormValue = {
  title: "",
  startDate: "",
  start: "",
  endDate: "",
  end: "",
  attendees: "",
  description: "",
  location: "",
}

export function fromWalls(start: WallTime, end: WallTime): FormValue {
  const opens = wallString(start)
  const closes = wallString(end)
  return {
    ...emptyForm,
    startDate: opens.slice(0, 10),
    start: opens.slice(11),
    endDate: closes.slice(0, 10),
    end: closes.slice(11),
  }
}

export function fromInstants(
  start: Date,
  end: Date,
  timeZone: string,
): FormValue {
  return fromWalls(wallTime(start, timeZone), wallTime(end, timeZone))
}

export function fromEvent(event: CalendarEvent, timeZone: string): FormValue {
  const when = event.all_day
    ? {
        ...emptyForm,
        startDate: event.start.slice(0, 10),
        endDate: event.start.slice(0, 10),
      }
    : fromInstants(new Date(event.start), new Date(event.end), timeZone)
  return {
    ...when,
    title: event.title,
    attendees: event.attendees.join(", "),
    description: event.description,
    location: event.location,
  }
}

export function attendeeList(text: string): string[] {
  return text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
}

export function startOf(value: FormValue): string {
  return `${value.startDate}T${value.start}`
}

export function endOf(value: FormValue): string {
  return `${value.endDate}T${value.end}`
}

export function withStartDate(value: FormValue, startDate: string): FormValue {
  return {
    ...value,
    startDate,
    endDate: followedEndDate(value.startDate, value.endDate, startDate),
  }
}

export function toFields(value: FormValue): EventFields {
  return {
    title: value.title.trim(),
    start: startOf(value),
    end: endOf(value),
    attendees: attendeeList(value.attendees),
    description: value.description,
    location: value.location,
  }
}

export function problem(value: FormValue, withTime: boolean): string | null {
  if (withTime) {
    if (!value.startDate || !value.start || !value.endDate || !value.end)
      return "Pick a start and an end."
    if (endOf(value) <= startOf(value))
      return "The end must be after the start."
  }
  const bad = attendeeList(value.attendees).find(
    (email) => !email.includes("@"),
  )
  if (bad) return `Not an email address: ${bad}`
  return null
}

export function shiftedInstant(
  instant: Date,
  days: number,
  minutes: number,
  timeZone: string,
): Date {
  const moved = instantOf(addDays(wallTime(instant, timeZone), days), timeZone)
  return new Date(moved.getTime() + minutes * 60000)
}
