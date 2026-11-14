import { cleanup, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, describe, expect, it } from "vitest"
import { DayCard } from "./DayCard"
import type { DayCardData } from "./types"

afterEach(cleanup)

const now = new Date("2026-11-06T10:00:00Z").getTime()

const card: DayCardData = {
  greeting: "Good morning, Alex.",
  meetings: [
    {
      event_id: "e1",
      title: "Call with Elena",
      start: "2026-11-06T10:25:00Z",
      end: "2026-11-06T10:55:00Z",
      attendees: ["Elena Park <elena@example.com>"],
      join_url: "https://meet.example.com/abc",
    },
    {
      event_id: "e2",
      title: "Review",
      start: "2026-11-06T15:00:00Z",
      end: "2026-11-06T15:30:00Z",
      attendees: [],
      join_url: null,
    },
  ],
  next_event_id: "e1",
  emails: [
    {
      thread_id: "t1",
      sender: "Rosa Lindqvist <rosa@example.com>",
      subject: "Revised proposal",
      received_at: "2026-11-06T08:00:00Z",
      reason: "Priority contact",
    },
  ],
  needs_you: 1,
  unread: 7,
  follow_ups: [],
  approvals: [{ id: 4, action: "mail_send", preview: "Send to Tomas" }],
  live: true,
  as_of: null,
}

function show(data: DayCardData) {
  render(
    <MemoryRouter>
      <DayCard card={data} now={now} />
    </MemoryRouter>,
  )
}

describe("DayCard", () => {
  it("greets and lists meetings with the next one counted down", () => {
    show(card)
    expect(screen.getByText("Good morning, Alex.")).toBeTruthy()
    expect(screen.getByText("in 25 min")).toBeTruthy()
    const meetings = screen.getByRole("region", { name: "2 meetings today" })
    const links = within(meetings).getAllByRole("link")
    expect(links.map((link) => link.textContent)).toEqual(["Join", "Open"])
    expect(links[0].getAttribute("href")).toBe("https://meet.example.com/abc")
    expect(links[1].getAttribute("href")).toBe("/calendar?event=e2")
    expect(within(meetings).getByText("Elena Park")).toBeTruthy()
  })

  it("links emails to the inbox thread and approvals to review", () => {
    show(card)
    const email = screen.getByRole("region", { name: "Emails that need you" })
    expect(within(email).getByRole("link").getAttribute("href")).toBe(
      "/inbox?thread=t1",
    )
    expect(
      within(email).getByText("Rosa Lindqvist · Priority contact"),
    ).toBeTruthy()
    const review = screen.getByRole("link", { name: "Review" })
    expect(review.getAttribute("href")).toBe("/approvals#approval-4")
    expect(screen.queryByRole("region", { name: "Follow-ups due" })).toBeNull()
  })

  it("says so when the day is quiet", () => {
    show({
      ...card,
      meetings: [],
      emails: [],
      approvals: [],
      next_event_id: null,
    })
    expect(screen.getByText("Nothing needs you right now.")).toBeTruthy()
  })
})
