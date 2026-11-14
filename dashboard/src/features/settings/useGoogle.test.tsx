import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { GoogleAccount } from "./GoogleAccount"
import type { GoogleStatus } from "./types"
import { POLL_MS } from "./useGoogle"

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const LINK = "https://accounts.google.com/o/oauth2/auth?client_id=test"

const status = (overrides: Partial<GoogleStatus>): GoogleStatus => ({
  state: "not_connected",
  email: null,
  connected_at: null,
  days_left: null,
  connecting: false,
  client_secret_found: true,
  client_secret_path: "/home/user/.homer/credentials/client_secret.json",
  auth_url: null,
  ...overrides,
})

const json = (body: unknown, code = 200) =>
  new Response(JSON.stringify(body), {
    status: code,
    headers: { "Content-Type": "application/json" },
  })

describe("google connect flow", () => {
  it("asks for the link without a browser and polls until the token lands", async () => {
    vi.useFakeTimers()
    const waiting = status({ connecting: true, auth_url: LINK })
    const connected = status({
      state: "connected",
      email: "tester@example.test",
      connected_at: "2026-11-14T09:00:00Z",
      days_left: 7,
    })
    const replies = [status({}), waiting, connected]
    const fetch = vi.fn(async (url: string) =>
      url.startsWith("/api/google/connect")
        ? json(waiting, 202)
        : json(replies.shift() ?? connected),
    )
    vi.stubGlobal("fetch", fetch)
    render(
      <QueryClientProvider client={new QueryClient()}>
        <GoogleAccount />
      </QueryClientProvider>,
    )
    await act(() => vi.advanceTimersByTimeAsync(0))
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Sign in with Google" }),
      )
      await vi.advanceTimersByTimeAsync(0)
    })
    const connect = fetch.mock.calls.find(([url]) =>
      url.startsWith("/api/google/connect"),
    )
    expect(connect?.[0]).toBe("/api/google/connect?no_browser=1")
    expect(screen.getByTestId("google-waiting").textContent).toContain(LINK)

    await act(() => vi.advanceTimersByTimeAsync(POLL_MS))
    expect(screen.getByTestId("google-waiting")).toBeTruthy()
    await act(() => vi.advanceTimersByTimeAsync(POLL_MS * 2))
    expect(screen.getByTestId("google-connected").textContent).toBe(
      "Connected as tester@example.test",
    )
    const polls = fetch.mock.calls.filter(
      ([url]) => url === "/api/google/status",
    )
    await act(() => vi.advanceTimersByTimeAsync(POLL_MS * 3))
    expect(
      fetch.mock.calls.filter(([url]) => url === "/api/google/status"),
    ).toHaveLength(polls.length)
  })
})
