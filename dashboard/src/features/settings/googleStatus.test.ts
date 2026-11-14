import { describe, expect, it } from "vitest"
import { bannerText, statusLabel } from "./googleStatus"
import type { GoogleStatus } from "./types"

const status = (fields: Partial<GoogleStatus>): GoogleStatus => ({
  state: "connected",
  email: null,
  connected_at: null,
  days_left: 7,
  connecting: false,
  client_secret_found: true,
  client_secret_path: "",
  ...fields,
})

describe("google status", () => {
  it("labels each state", () => {
    expect(statusLabel(status({}))).toBe("Connected")
    expect(statusLabel(status({ state: "expiring", days_left: 2 }))).toBe(
      "Expires in 2 days",
    )
    expect(statusLabel(status({ state: "expiring", days_left: 1 }))).toBe(
      "Expires in 1 day",
    )
    expect(statusLabel(status({ state: "expired", days_left: 0 }))).toBe(
      "Expired",
    )
    expect(statusLabel(status({ state: "not_connected" }))).toBe(
      "Not connected",
    )
  })

  it("shows a banner only from day five", () => {
    expect(bannerText(status({}))).toBeNull()
    expect(bannerText(undefined)).toBeNull()
    expect(bannerText(status({ state: "expiring", days_left: 2 }))).toBe(
      "Google disconnects in 2 days. Reconnect now.",
    )
    expect(bannerText(status({ state: "expired", days_left: 0 }))).toBe(
      "Google is disconnected. Reconnect now.",
    )
  })
})
