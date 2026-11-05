import { describe, expect, it } from "vitest"
import { addDays, instantOf, parseWall, wallString, wallTime } from "./zoned"

describe("zoned time", () => {
  it("reads an instant as wall time in another zone", () => {
    const instant = new Date("2026-11-06T09:30:00Z")
    expect(wallString(wallTime(instant, "Asia/Karachi"))).toBe(
      "2026-11-06T14:30",
    )
    expect(wallString(wallTime(instant, "America/New_York"))).toBe(
      "2026-11-06T04:30",
    )
  })

  it("turns wall time back into the instant, across a DST change", () => {
    const summer = instantOf(parseWall("2026-07-01T09:00"), "Europe/London")
    expect(summer.toISOString()).toBe("2026-07-01T08:00:00.000Z")
    const winter = instantOf(parseWall("2026-11-02T09:00"), "Europe/London")
    expect(winter.toISOString()).toBe("2026-11-02T09:00:00.000Z")
  })

  it("adds days over month ends", () => {
    expect(addDays({ year: 2026, month: 1, day: 31 }, 1)).toEqual({
      year: 2026,
      month: 2,
      day: 1,
    })
  })
})
