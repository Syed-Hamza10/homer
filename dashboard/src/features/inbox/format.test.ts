import { describe, expect, it } from "vitest"
import { displayName, fileSize, shortDate, splitQuote } from "./format"

describe("inbox formatting", () => {
  it("shows the display name of an address", () => {
    expect(displayName("Maya Lindqvist <maya@example.test>")).toBe(
      "Maya Lindqvist",
    )
    expect(displayName('"Ops" <ops@example.test>')).toBe("Ops")
    expect(displayName("<ops@example.test>")).toBe("ops@example.test")
    expect(displayName("ops@example.test")).toBe("ops@example.test")
  })

  it("shows the time for today and the day otherwise, in the user's zone", () => {
    const now = new Date("2026-11-06T10:00:00Z")
    expect(shortDate("2026-11-06T20:30:00Z", "Asia/Karachi", now)).toMatch(
      /7.*Nov|Nov.*7/,
    )
    expect(shortDate("2026-11-06T08:15:00Z", "UTC", now)).toMatch(/08:15/)
    expect(shortDate("2026-11-05T08:15:00Z", "UTC", now)).toMatch(/Nov/)
    expect(shortDate("2025-01-05T08:15:00Z", "UTC", now)).toMatch(/2025/)
  })

  it("keeps the quoted part apart from the new text", () => {
    const body = "\n\nOn Thu, Maya wrote:\n> Hi"
    expect(splitQuote(`Thanks${body}`)).toEqual({ text: "Thanks", quote: body })
    expect(splitQuote("Just text")).toEqual({ text: "Just text", quote: "" })
  })

  it("prints file sizes", () => {
    expect(fileSize(48213)).toBe("47 KB")
  })
})
