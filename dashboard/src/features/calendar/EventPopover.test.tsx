import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { EventPopover } from "./EventPopover"
import type { CalendarEvent } from "./types"

const meeting: CalendarEvent = {
  id: "evt_1",
  title: "Kickoff",
  start: "2026-11-06T09:00:00Z",
  end: "2026-11-06T10:00:00Z",
  all_day: false,
  location: "Online",
  description: "Agenda first.",
  attendees: ["maya@example.test"],
  people: [
    {
      email: "maya@example.test",
      name: "Maya",
      response: "accepted",
      organizer: false,
    },
  ],
  organizer: "me@example.test",
  video_link: "https://meet.example.test/abc",
}

function show() {
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <EventPopover
        event={meeting}
        timeZone="Asia/Karachi"
        onClose={() => {}}
        onApproval={() => {}}
      />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe("EventPopover", () => {
  it("shows the details in the user's timezone", () => {
    show()
    expect(screen.getByText("Kickoff")).toBeTruthy()
    expect(screen.getByText(/14:00–15:00/)).toBeTruthy()
    expect(screen.getByText("Accepted")).toBeTruthy()
    const link = screen.getByRole("link", { name: /Join video call/ })
    expect(link.getAttribute("target")).toBe("_blank")
    expect(link.getAttribute("rel")).toContain("noopener")
  })

  it("asks for a move with local wall times", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 7,
          action: "cal_update",
          preview: "Move",
          payload: {},
        }),
      ),
    )
    vi.stubGlobal("fetch", fetchMock)
    show()
    fireEvent.click(screen.getByRole("button", { name: "Move" }))
    fireEvent.change(screen.getByLabelText("Start time"), {
      target: { value: "16:00" },
    })
    fireEvent.change(screen.getByLabelText("End time"), {
      target: { value: "17:00" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Ask to move" }))
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("/api/calendar/events/evt_1")
    expect(init.method).toBe("PATCH")
    expect(JSON.parse(init.body)).toEqual({
      start: "2026-11-06T16:00",
      end: "2026-11-06T17:00",
    })
  })

  it("moves an event across midnight with its own end date", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 8,
          action: "cal_update",
          preview: "Move",
          payload: {},
        }),
      ),
    )
    vi.stubGlobal("fetch", fetchMock)
    show()
    fireEvent.click(screen.getByRole("button", { name: "Move" }))
    fireEvent.change(screen.getByLabelText("Start time"), {
      target: { value: "23:00" },
    })
    fireEvent.change(screen.getByLabelText("End time"), {
      target: { value: "01:00" },
    })
    expect(screen.getByText("The end must be after the start.")).toBeTruthy()
    fireEvent.change(screen.getByLabelText("End date"), {
      target: { value: "2026-11-07" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Ask to move" }))
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      start: "2026-11-06T23:00",
      end: "2026-11-07T01:00",
    })
  })
})
