import { formatIn, wallTime } from "@/lib/zoned"

export function displayName(address: string): string {
  const match = address.match(/^\s*"?([^"<]*?)"?\s*<([^>]+)>\s*$/)
  if (!match) return address.trim()
  return match[1].trim() || match[2].trim()
}

export function shortDate(iso: string, timeZone: string, now = new Date()) {
  const instant = new Date(iso)
  const day = wallTime(instant, timeZone)
  const today = wallTime(now, timeZone)
  if (
    day.year === today.year &&
    day.month === today.month &&
    day.day === today.day
  )
    return formatIn(instant, timeZone, { hour: "2-digit", minute: "2-digit" })
  if (day.year === today.year)
    return formatIn(instant, timeZone, { day: "numeric", month: "short" })
  return formatIn(instant, timeZone, {
    day: "numeric",
    month: "short",
    year: "numeric",
  })
}

export function longDate(iso: string, timeZone: string): string {
  return formatIn(new Date(iso), timeZone, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function splitQuote(body: string): { text: string; quote: string } {
  const at = body.search(/\n\n(On .+ wrote:|-{10} Forwarded message -{10})/)
  if (at === -1) return { text: body, quote: "" }
  return { text: body.slice(0, at), quote: body.slice(at) }
}
