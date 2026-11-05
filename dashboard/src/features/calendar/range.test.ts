import { describe, expect, it } from "vitest"
import { rangeOf, shift, visibleDays } from "./range"

describe("calendar range", () => {
  it("starts weeks on Monday and months on a full grid", () => {
    const friday = { year: 2026, month: 11, day: 6 }
    expect(visibleDays("week", friday)[0]).toEqual({
      year: 2026,
      month: 11,
      day: 2,
    })
    const month = visibleDays("month", friday)
    expect(month).toHaveLength(42)
    expect(month[0]).toEqual({ year: 2026, month: 10, day: 26 })
  })

  it("turns the visible days into instants in the user's timezone", () => {
    const { start, end } = rangeOf(
      visibleDays("day", { year: 2026, month: 11, day: 6 }),
      "Asia/Karachi",
    )
    expect(start.toISOString()).toBe("2026-11-05T19:00:00.000Z")
    expect(end.toISOString()).toBe("2026-11-06T19:00:00.000Z")
  })

  it("steps months across the year end", () => {
    expect(shift("month", { year: 2026, month: 12, day: 15 }, 1)).toEqual({
      year: 2027,
      month: 1,
      day: 1,
    })
  })
})
