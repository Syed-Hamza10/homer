import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CalendarPage } from "./CalendarPage"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function Where() {
  return <output data-testid="where">{useLocation().search}</output>
}

function renderPage(entry = "/calendar") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url.startsWith("/api/settings")
        ? new Response(JSON.stringify({ timezone: "UTC" }))
        : new Response(JSON.stringify({ events: [], source: "google" })),
    ),
  )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/calendar"
            element={
              <>
                <CalendarPage />
                <Where />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const pressed = (name: string) =>
  screen.getByRole("button", { name }).getAttribute("aria-pressed")

describe("CalendarPage shortcuts", () => {
  it("switches views, steps periods and returns to today", () => {
    renderPage()
    expect(pressed("Week")).toBe("true")
    fireEvent.keyDown(window, { key: "m" })
    expect(pressed("Month")).toBe("true")
    fireEvent.keyDown(window, { key: "d" })
    expect(pressed("Day")).toBe("true")
    const today = screen.getByTestId("calendar-title").textContent
    fireEvent.keyDown(window, { key: "j" })
    fireEvent.keyDown(window, { key: "ArrowRight" })
    const later = screen.getByTestId("calendar-title").textContent
    expect(later).not.toBe(today)
    fireEvent.keyDown(window, { key: "k" })
    fireEvent.keyDown(window, { key: "ArrowLeft" })
    expect(screen.getByTestId("calendar-title").textContent).toBe(today)
    fireEvent.keyDown(window, { key: "j" })
    fireEvent.keyDown(window, { key: "t" })
    expect(screen.getByTestId("calendar-title").textContent).toBe(today)
    fireEvent.keyDown(window, { key: "w" })
    expect(pressed("Week")).toBe("true")
  })

  it("opens quick create on c and the cheat sheet on ?", () => {
    renderPage()
    fireEvent.keyDown(window, { key: "c" })
    expect(screen.getByTestId("quick-create")).toBeTruthy()
    fireEvent.keyDown(window, { key: "?" })
    expect(
      screen.getByRole("dialog", { name: "Calendar keyboard shortcuts" }),
    ).toBeTruthy()
  })
})

describe("CalendarPage URL", () => {
  it("restores the view and date from the URL and keeps them there", () => {
    renderPage("/calendar?view=month&date=2026-11-16")
    expect(pressed("Month")).toBe("true")
    expect(screen.getByTestId("calendar-title").textContent).toBe(
      "November 2026",
    )
    fireEvent.keyDown(window, { key: "j" })
    expect(screen.getByTestId("where").textContent).toBe(
      "?view=month&date=2026-12-01",
    )
    fireEvent.keyDown(window, { key: "w" })
    expect(screen.getByTestId("where").textContent).toBe(
      "?view=week&date=2026-12-01",
    )
    fireEvent.keyDown(window, { key: "t" })
    expect(screen.getByTestId("where").textContent).toBe("?view=week")
  })
})
