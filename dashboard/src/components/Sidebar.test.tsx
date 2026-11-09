import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { AppShell } from "./AppShell"

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("[]")),
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderAt(path: string) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="*" element={<p>page</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("Sidebar", () => {
  it("lists recent chats only on the chat page", () => {
    renderAt("/")
    expect(screen.getByRole("region", { name: "Recent chats" })).toBeTruthy()
    cleanup()
    renderAt("/inbox")
    expect(screen.queryByRole("region", { name: "Recent chats" })).toBeNull()
  })

  it("collapses to icons and remembers it", () => {
    renderAt("/")
    fireEvent.click(
      screen.getAllByRole("button", { name: "Collapse sidebar" })[0],
    )
    expect(localStorage.getItem("homer.sidebar.collapsed")).toBe("1")
    expect(screen.queryByRole("region", { name: "Recent chats" })).toBeNull()
    cleanup()
    renderAt("/")
    expect(
      screen.getAllByRole("button", { name: "Expand sidebar" }),
    ).toHaveLength(1)
  })

  it("opens the search field from the icon", () => {
    renderAt("/")
    fireEvent.click(
      screen.getByRole("button", { name: "Search conversations" }),
    )
    expect(
      screen.getByRole("searchbox", { name: "Search conversations" }),
    ).toBeTruthy()
  })
})
