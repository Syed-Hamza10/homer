export type WallTime = {
  year: number
  month: number
  day: number
  hour: number
  minute: number
}

const partsFormatters = new Map<string, Intl.DateTimeFormat>()

function partsFormatter(timeZone: string): Intl.DateTimeFormat {
  let formatter = partsFormatters.get(timeZone)
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-US", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "numeric",
    })
    partsFormatters.set(timeZone, formatter)
  }
  return formatter
}

export function wallTime(instant: Date, timeZone: string): WallTime {
  const parts = Object.fromEntries(
    partsFormatter(timeZone)
      .formatToParts(instant)
      .map((part) => [part.type, part.value]),
  )
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour) % 24,
    minute: Number(parts.minute),
  }
}

function asUtc(wall: WallTime): number {
  return Date.UTC(wall.year, wall.month - 1, wall.day, wall.hour, wall.minute)
}

function offsetAt(time: number, timeZone: string): number {
  return asUtc(wallTime(new Date(time), timeZone)) - time
}

export function instantOf(wall: WallTime, timeZone: string): Date {
  const guess = asUtc(wall)
  const first = guess - offsetAt(guess, timeZone)
  return new Date(guess - offsetAt(first, timeZone))
}

const pad = (value: number) => String(value).padStart(2, "0")

export function dateKey(wall: Pick<WallTime, "year" | "month" | "day">) {
  return `${wall.year}-${pad(wall.month)}-${pad(wall.day)}`
}

export function wallString(wall: WallTime): string {
  return `${dateKey(wall)}T${pad(wall.hour)}:${pad(wall.minute)}`
}

export function parseWall(value: string): WallTime {
  const [date, clock = "00:00"] = value.split("T")
  const [year, month, day] = date.split("-").map(Number)
  const [hour, minute] = clock.split(":").map(Number)
  return { year, month, day, hour, minute }
}

export function addDays<T extends Pick<WallTime, "year" | "month" | "day">>(
  wall: T,
  days: number,
): T {
  const shifted = new Date(Date.UTC(wall.year, wall.month - 1, wall.day + days))
  return {
    ...wall,
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth() + 1,
    day: shifted.getUTCDate(),
  }
}

export function weekdayOf(wall: Pick<WallTime, "year" | "month" | "day">) {
  return new Date(Date.UTC(wall.year, wall.month - 1, wall.day)).getUTCDay()
}

export function formatIn(
  instant: Date,
  timeZone: string,
  options: Intl.DateTimeFormatOptions,
): string {
  return new Intl.DateTimeFormat(undefined, { timeZone, ...options }).format(
    instant,
  )
}

export function browserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}
