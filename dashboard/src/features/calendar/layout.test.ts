import { describe, expect, it } from "vitest"
import { allDayOn, placeSegments, segmentsForDay } from "./layout"
import type { CalendarEvent } from "./types"

function event(id: string, start: string, end: string, allDay = false) {
  return {
    id,
    title: id,
    start,
    end,
    all_day: allDay,
    location: "",
    description: "",
    attendees: [],
    people: [],
    organizer: "",
    video_link: "",
  } satisfies CalendarEvent
}

const day = { year: 2026, month: 11, day: 6 }

describe("calendar layout", () => {
  it("clips events to the day in the user's timezone", () => {
    const events = [
      event("late", "2026-11-05T22:00:00Z", "2026-11-06T01:00:00Z"),
      event("other", "2026-11-07T09:00:00Z", "2026-11-07T10:00:00Z"),
      event("tiny", "2026-11-06T12:00:00Z", "2026-11-06T12:05:00Z"),
    ]
    const segments = segmentsForDay(events, day, "Asia/Karachi")
    expect(segments.map((s) => [s.event.id, s.top, s.bottom])).toEqual([
      ["late", 180, 360],
      ["tiny", 1020, 1035],
    ])
  })

  it("lays overlapping events side by side", () => {
    const placed = placeSegments([
      { event: event("a", "", ""), top: 540, bottom: 600 },
      { event: event("b", "", ""), top: 570, bottom: 630 },
      { event: event("c", "", ""), top: 600, bottom: 660 },
      { event: event("d", "", ""), top: 720, bottom: 780 },
    ])
    const shape = Object.fromEntries(
      placed.map((p) => [p.event.id, [p.column, p.columns]]),
    )
    expect(shape).toEqual({ a: [0, 2], b: [1, 2], c: [0, 2], d: [0, 1] })
  })

  it("puts all-day events on each covered day, end exclusive", () => {
    const offsite = event("offsite", "2026-11-05", "2026-11-07", true)
    expect(allDayOn([offsite], day)).toEqual([offsite])
    expect(allDayOn([offsite], { ...day, day: 7 })).toEqual([])
  })
})
