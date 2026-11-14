import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { Link, MemoryRouter } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"
import { LEAVE_WARNING } from "@/lib/useLeaveWarning"
import { SettingsPage } from "./SettingsPage"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const rules = {
  signature: "Jordan",
  tone: "warm",
  business_hours: "09:00-17:00",
  follow_up_days: 3,
  priority_contacts: [],
  email_to_self: false,
  self_email: "",
  model_tier: null,
  timezone: "UTC",
}

function stub(loadFails = { count: 0 }) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/settings" && init?.method === "PUT")
      return new Response(String(init.body))
    if (url === "/api/settings") {
      if (loadFails.count > 0) {
        loadFails.count -= 1
        return new Response("{}", { status: 500 })
      }
      return new Response(JSON.stringify(rules))
    }
    return new Response("{}", { status: 404 })
  })
  vi.stubGlobal("fetch", fetch)
  return fetch
}

function renderPage() {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <Link to="/inbox">Inbox</Link>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("SettingsPage", () => {
  it("shows Unsaved changes after an edit and Saved only after saving", async () => {
    stub()
    renderPage()
    const tone = await screen.findByDisplayValue("warm")
    const save = screen.getByRole("button", { name: "Save" })
    expect(save.hasAttribute("disabled")).toBe(true)
    fireEvent.change(tone, { target: { value: "brief" } })
    expect(screen.getByText("Unsaved changes")).toBeTruthy()
    expect(save.hasAttribute("disabled")).toBe(false)
    fireEvent.click(save)
    expect(await screen.findByText("Saved.")).toBeTruthy()
    fireEvent.change(tone, { target: { value: "brief and kind" } })
    expect(screen.queryByText("Saved.")).toBeNull()
    expect(screen.getByText("Unsaved changes")).toBeTruthy()
  })

  it("asks before leaving with unsaved changes", async () => {
    stub()
    renderPage()
    fireEvent.change(await screen.findByDisplayValue("warm"), {
      target: { value: "brief" },
    })
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    const event = new MouseEvent("click", { bubbles: true, cancelable: true })
    screen.getByRole("link", { name: "Inbox" }).dispatchEvent(event)
    expect(confirm).toHaveBeenCalledWith(LEAVE_WARNING)
    expect(event.defaultPrevented).toBe(true)
  })

  it("explains a failed load and loads again on Try again", async () => {
    stub({ count: 1 })
    renderPage()
    expect(
      await screen.findByText(/Could not load your preferences\./),
    ).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Try again" }))
    await waitFor(() => expect(screen.getByDisplayValue("warm")).toBeTruthy())
  })
})
