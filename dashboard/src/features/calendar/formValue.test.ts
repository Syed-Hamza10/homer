import { describe, expect, it } from "vitest"
import { emptyForm, problem, toFields, withStartDate } from "./formValue"

const overnight = {
  ...emptyForm,
  title: "Launch watch",
  startDate: "2026-11-20",
  start: "23:00",
  endDate: "2026-11-21",
  end: "01:00",
}

describe("event form value", () => {
  it("accepts an event that crosses midnight", () => {
    expect(problem(overnight, true)).toBeNull()
    expect(toFields(overnight)).toMatchObject({
      start: "2026-11-20T23:00",
      end: "2026-11-21T01:00",
    })
  })

  it("rejects an end before the start across days", () => {
    expect(problem({ ...overnight, endDate: "2026-11-20" }, true)).toBe(
      "The end must be after the start.",
    )
  })

  it("moves a same-day end date along with the start date", () => {
    const sameDay = { ...overnight, endDate: "2026-11-20" }
    expect(withStartDate(sameDay, "2026-11-22").endDate).toBe("2026-11-22")
    expect(withStartDate(overnight, "2026-11-19").endDate).toBe("2026-11-21")
  })
})
