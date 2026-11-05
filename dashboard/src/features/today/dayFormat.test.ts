import { describe, expect, it } from "vitest"
import { attendeeLine, personName, untilLabel } from "./dayFormat"

const now = new Date("2026-11-06T10:00:00Z").getTime()

describe("untilLabel", () => {
  it("counts down to the next meeting", () => {
    expect(
      untilLabel("2026-11-06T10:25:00Z", "2026-11-06T10:55:00Z", now),
    ).toBe("in 25 min")
    expect(
      untilLabel("2026-11-06T12:05:00Z", "2026-11-06T13:00:00Z", now),
    ).toBe("in 2 h 5 min")
    expect(
      untilLabel("2026-11-06T11:00:00Z", "2026-11-06T12:00:00Z", now),
    ).toBe("in 1 h")
  })

  it("says now during a meeting and nothing after it", () => {
    expect(
      untilLabel("2026-11-06T09:50:00Z", "2026-11-06T10:20:00Z", now),
    ).toBe("now")
    expect(
      untilLabel("2026-11-06T09:00:00Z", "2026-11-06T09:30:00Z", now),
    ).toBe("")
  })
})

describe("names", () => {
  it("prefers the display name and shortens long lists", () => {
    expect(personName('"Rosa Lindqvist" <rosa@example.com>')).toBe(
      "Rosa Lindqvist",
    )
    expect(personName("<dana@example.com>")).toBe("dana@example.com")
    expect(attendeeLine(["a@x.com", "b@x.com", "c@x.com", "d@x.com"])).toBe(
      "a@x.com, b@x.com, c@x.com +1",
    )
  })
})
