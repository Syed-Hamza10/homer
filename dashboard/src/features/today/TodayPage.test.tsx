import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"
import { TodayPage } from "./TodayPage"
import type { Today } from "./types"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const brief = {
  kind: "morning" as const,
  day: "2026-11-14",
  content: "Good morning, Hamza. Nothing on your calendar today.",
  generated_at: "2026-11-14T07:30:00",
}

const digest = {
  kind: "digest" as const,
  day: "2026-11-14",
  content: "Good evening, Hamza. Nothing on your calendar tomorrow.",
  generated_at: "2026-11-14T18:00:00",
}

function today(overrides: Partial<Today> = {}): Today {
  return {
    day: "2026-11-14",
    brief,
    digest,
    showing: "digest",
    reminders: [],
    follow_ups: [],
    background_refresh: true,
    health: null,
    google: {
      state: "connected",
      email: "owner@example.test",
      connected_at: null,
      days_left: null,
      connecting: false,
      client_secret_found: true,
      client_secret_path: "",
    },
    card: {
      greeting: "Good afternoon, Hamza.",
      meetings: [],
      next_event_id: null,
      emails: [],
      needs_you: 2,
      unread: 24,
      follow_ups: [],
      approvals: [],
      live: true,
      as_of: null,
    },
    ...overrides,
  } as Today
}

function show(data: Today) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) =>
    init?.method === "POST"
      ? new Response(JSON.stringify(url.endsWith("/digest") ? digest : brief))
      : new Response(JSON.stringify(data)),
  )
  vi.stubGlobal("fetch", fetch)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <TodayPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return fetch
}

describe("TodayPage", () => {
  it("takes the header counts from the day card", async () => {
    show(today())
    expect(
      await screen.findByText("24 unread · 0 waiting for approval"),
    ).toBeTruthy()
    expect(
      screen.getByText("0 meetings · 2 emails need you · 0 approvals waiting"),
    ).toBeTruthy()
    expect(screen.queryByTestId("refresh-note")).toBeNull()
  })

  it("shows only the brief for this time of day, with the other a click away", async () => {
    show(today())
    const panel = await screen.findByTestId("brief-panel")
    expect(
      within(panel).getByText("End-of-day digest · generated 18:00"),
    ).toBeTruthy()
    expect(within(panel).getByText(digest.content)).toBeTruthy()
    expect(within(panel).queryByText(brief.content)).toBeNull()
    fireEvent.click(within(panel).getByText("See the morning brief"))
    expect(
      within(panel).getByText("Morning brief · generated 07:30"),
    ).toBeTruthy()
    expect(within(panel).getByText(brief.content)).toBeTruthy()
  })

  it("refreshes the brief that is showing", async () => {
    const fetch = show(today({ showing: "morning" }))
    const panel = await screen.findByTestId("brief-panel")
    fireEvent.click(within(panel).getByRole("button", { name: "Refresh" }))
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        "/api/today/brief",
        expect.objectContaining({ method: "POST" }),
      ),
    )
  })

  it("says when background refresh is off and when Google is not answering", async () => {
    show(
      today({
        background_refresh: false,
        card: { ...today().card, live: false, as_of: "2026-11-14T16:05:00" },
      }),
    )
    expect(await screen.findByText("Background refresh is off")).toBeTruthy()
    expect(screen.getByTestId("stale-note").textContent).toBe(
      "Google is not answering · as of 16:05",
    )
  })
})
