import type { GoogleStatus } from "./types"

function days(count: number | null): string {
  return count === 1 ? "1 day" : `${count ?? 0} days`
}

export function statusLabel(status: GoogleStatus): string {
  switch (status.state) {
    case "connected":
      return "Connected"
    case "expiring":
      return `Expires in ${days(status.days_left)}`
    case "expired":
      return "Expired"
    default:
      return "Not connected"
  }
}

export function bannerText(status: GoogleStatus | undefined): string | null {
  if (status?.state === "expiring")
    return `Google disconnects in ${days(status.days_left)}. Reconnect now.`
  if (status?.state === "expired")
    return "Google is disconnected. Reconnect now."
  return null
}
