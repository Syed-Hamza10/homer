const MINUTE_MS = 60_000

export function updatedText(at: number, now: number): string {
  const minutes = Math.floor((now - at) / MINUTE_MS)
  if (minutes < 1) return "Updated just now"
  if (minutes === 1) return "Updated 1 minute ago"
  return `Updated ${minutes} minutes ago`
}
