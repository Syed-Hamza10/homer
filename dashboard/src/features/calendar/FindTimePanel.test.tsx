import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { FindTimePanel } from "./FindTimePanel"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const slotAt = (hour: number, minutes: number) => ({
  start: `2026-11-20T${hour}:00:00Z`,
  end: `2026-11-20T${hour}:${String(minutes).padStart(2, "0")}:00Z`,
})

describe("FindTimePanel", () => {
  it("disables old times and asks again when the length changes", async () => {
    const asked: number[] = []
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_: string, init: RequestInit) => {
        const { duration_minutes } = JSON.parse(String(init.body)) as {
          duration_minutes: number
        }
        asked.push(duration_minutes)
        return new Response(
          JSON.stringify([slotAt(duration_minutes === 30 ? 10 : 14, 30)]),
        )
      }),
    )
    const onPick = vi.fn()
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FindTimePanel timeZone="UTC" onClose={vi.fn()} onPick={onPick} />
      </QueryClientProvider>,
    )
    fireEvent.change(screen.getByLabelText("Attendees (comma separated)"), {
      target: { value: "sam@example.test" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Find free times" }))
    const first = await screen.findByRole("button", { name: /10:00/ })
    expect(first.hasAttribute("disabled")).toBe(false)
    fireEvent.change(screen.getByLabelText("Length (minutes)"), {
      target: { value: "60" },
    })
    expect(
      screen.getByRole("button", { name: /10:00/ }).hasAttribute("disabled"),
    ).toBe(true)
    const next = await screen.findByRole("button", { name: /14:00/ })
    expect(next.hasAttribute("disabled")).toBe(false)
    await waitFor(() => expect(asked).toEqual([30, 60]))
    expect(screen.queryByRole("button", { name: /10:00/ })).toBeNull()
  })
})
