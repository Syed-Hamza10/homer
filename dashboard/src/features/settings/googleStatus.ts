import type { GoogleStatus } from "./types"

export type ConnectStep = "missing" | "ready" | "waiting" | "connected"

export function connectStep(status: GoogleStatus): ConnectStep {
  if (status.connecting && status.auth_url) return "waiting"
  if (status.state === "connected" || status.state === "expiring")
    return "connected"
  return status.client_secret_found ? "ready" : "missing"
}

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
