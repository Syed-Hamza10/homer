import { describe, expect, it } from "vitest"
import { bannerText, connectStep, statusLabel } from "./googleStatus"
import type { GoogleStatus } from "./types"

const status = (fields: Partial<GoogleStatus>): GoogleStatus => ({
  state: "connected",
  email: null,
  connected_at: null,
  days_left: 7,
  connecting: false,
  client_secret_found: true,
  client_secret_path: "",
  auth_url: null,
  ...fields,
})

describe("google status", () => {
  it("picks the connect step", () => {
    const signedOut = { state: "not_connected" as const, days_left: null }
    expect(
      connectStep(status({ ...signedOut, client_secret_found: false })),
    ).toBe("missing")
    expect(connectStep(status(signedOut))).toBe("ready")
    expect(connectStep(status({ state: "expired", days_left: 0 }))).toBe(
      "ready",
    )
    expect(
      connectStep(
        status({ ...signedOut, connecting: true, auth_url: "https://x" }),
      ),
    ).toBe("waiting")
    expect(connectStep(status({}))).toBe("connected")
    expect(connectStep(status({ state: "expiring", days_left: 1 }))).toBe(
      "connected",
    )
  })

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
