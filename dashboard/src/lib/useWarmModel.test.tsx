import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { WARM_MS, useWarmModel } from "./useWarmModel"

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function Probe() {
  useWarmModel()
  return null
}

describe("useWarmModel", () => {
  it("warms the model on open and every four minutes", async () => {
    vi.useFakeTimers()
    const fetch = vi.fn<(url: string) => Promise<Response>>(
      async () => new Response(null, { status: 204 }),
    )
    vi.stubGlobal("fetch", fetch)
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Probe />
      </QueryClientProvider>,
    )
    await act(() => vi.advanceTimersByTimeAsync(0))
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0][0]).toBe("/api/model/warm")
    await act(() => vi.advanceTimersByTimeAsync(WARM_MS))
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
