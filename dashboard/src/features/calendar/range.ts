import { addDays, instantOf, weekdayOf } from "@/lib/zoned"
import type { DateOnly, View } from "./types"

export function startOfWeek(day: DateOnly): DateOnly {
  return addDays(day, -((weekdayOf(day) + 6) % 7))
}

export function visibleDays(view: View, anchor: DateOnly): DateOnly[] {
  if (view === "day") return [anchor]
  const first =
    view === "week" ? startOfWeek(anchor) : startOfWeek({ ...anchor, day: 1 })
  const count = view === "week" ? 7 : 42
  return Array.from({ length: count }, (_, index) => addDays(first, index))
}

export function rangeOf(days: DateOnly[], timeZone: string) {
  const last = addDays(days[days.length - 1], 1)
  return {
    start: instantOf({ ...days[0], hour: 0, minute: 0 }, timeZone),
    end: instantOf({ ...last, hour: 0, minute: 0 }, timeZone),
  }
}

export function shift(view: View, anchor: DateOnly, step: number): DateOnly {
  if (view === "day") return addDays(anchor, step)
  if (view === "week") return addDays(anchor, step * 7)
  const index = anchor.year * 12 + anchor.month - 1 + step
  return { year: Math.floor(index / 12), month: (index % 12) + 1, day: 1 }
}

export function dayLabel(
  day: DateOnly,
  options: Intl.DateTimeFormatOptions,
): string {
  const noon = new Date(Date.UTC(day.year, day.month - 1, day.day, 12))
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    ...options,
  }).format(noon)
}

export function rangeTitle(
  view: View,
  days: DateOnly[],
  anchor: DateOnly,
): string {
  if (view === "day")
    return dayLabel(anchor, {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    })
  if (view === "month")
    return dayLabel({ ...anchor, day: 1 }, { month: "long", year: "numeric" })
  const first = dayLabel(days[0], { day: "numeric", month: "short" })
  const last = dayLabel(days[days.length - 1], {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
  return `${first} – ${last}`
}

const views: View[] = ["day", "week", "month"]

export function viewParam(value: string | null): View | null {
  return views.find((view) => view === value) ?? null
}

export function dateParam(value: string | null): DateOnly | null {
  const match = value?.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return null
  const [year, month, day] = match.slice(1).map(Number)
  const check = new Date(Date.UTC(year, month - 1, day))
  return check.getUTCMonth() === month - 1 && check.getUTCDate() === day
    ? { year, month, day }
    : null
}
