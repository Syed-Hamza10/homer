import { describe, expect, it } from "vitest"
import { healthLine } from "./healthLine"
import type { Health } from "./types"

const now = Date.parse("2026-11-10T10:00:00Z")

const health = (fields: Partial<Health>): Health => ({
  ollama: "ok",
  model_pulled: "ok",
  model_status: "running",
  servers: { google: "ok", search: "ok" },
  self_email: "off",
  checked_at: "2026-11-10T10:00:00Z",
  ...fields,
})

describe("health line", () => {
  it("starts with the model status", () => {
    expect(healthLine(health({}), now)).toBe(
      "Model running · All systems OK · checked just now",
    )
  })

  it("says when the model is not running", () => {
    const line = healthLine(
      health({ ollama: "down", model_status: "stopped" }),
      now,
    )
    expect(line).toBe(
      "The AI model isn't running · All systems OK · checked just now",
    )
  })

  it("lists services that are down", () => {
    const line = healthLine(
      health({ servers: { google: "ok", search: "down" } }),
      now,
    )
    expect(line).toBe(
      "Model running · Web search is not responding · checked just now",
    )
  })

  it("is empty without a report", () => {
    expect(healthLine(null)).toBeNull()
  })
})
