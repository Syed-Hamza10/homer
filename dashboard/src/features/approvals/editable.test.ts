import { describe, expect, it } from "vitest"
import { editsGuests, eventFields, eventOrderProblem } from "./editable"

describe("eventFields", () => {
  it("reads a move card's new time and current title", () => {
    const move = {
      id: 6,
      action: "cal_update",
      preview:
        "Move 'Lunch with Sam' from Wed 18 Nov 13:00-14:00 to Wed 18 Nov 15:00-16:00",
      payload: {
        event_id: "evt_0005",
        changes: {
          start: "2026-11-18T15:00:00+05:00",
          end: "2026-11-18T16:00:00+05:00",
        },
      },
    }
    expect(eventFields(move)).toEqual({
      title: "Lunch with Sam",
      date: "2026-11-18",
      end_date: "2026-11-18",
      start: "15:00",
      end: "16:00",
      attendees: [],
    })
    expect(editsGuests("cal_update")).toBe(false)
    expect(editsGuests("cal_create")).toBe(true)
  })

  it("offers no edit for a delete card", () => {
    const remove = {
      id: 7,
      action: "cal_delete",
      preview: "Delete 'Lunch'",
      payload: { event_id: "evt_0005" },
    }
    expect(eventFields(remove)).toBeNull()
  })

  it("keeps an event that crosses midnight on two dates", () => {
    const overnight = eventFields({
      id: 8,
      action: "cal_create",
      preview: "Create 'Launch watch'",
      payload: {
        title: "Launch watch",
        start: "2026-11-20T23:00:00",
        end: "2026-11-21T01:00:00",
        attendees: [],
      },
    })
    expect(overnight).toMatchObject({
      date: "2026-11-20",
      start: "23:00",
      end_date: "2026-11-21",
      end: "01:00",
    })
    expect(overnight && eventOrderProblem(overnight)).toBeNull()
    expect(
      overnight && eventOrderProblem({ ...overnight, end_date: "2026-11-20" }),
    ).toBe("The end must be after the start.")
  })
})
