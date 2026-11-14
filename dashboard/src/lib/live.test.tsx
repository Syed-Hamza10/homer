import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query"
import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { LIVE_MS, liveQuery, refetchOnWindowFocus } from "./live"
import { updatedText } from "./updatedText"

afterEach(cleanup)

function Probe({ load }: { load: () => Promise<number> }) {
  const { data } = useQuery({
    queryKey: ["probe"],
    queryFn: load,
    ...liveQuery,
  })
  return <p data-testid="probe">{data}</p>
}

describe("live queries", () => {
  it("refetch when the window regains focus and poll every minute", async () => {
    refetchOnWindowFocus()
    let calls = 0
    const load = vi.fn(async () => ++calls)
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Probe load={load} />
      </QueryClientProvider>,
    )
    expect(await screen.findByText("1")).toBeTruthy()
    act(() => {
      window.dispatchEvent(new Event("focus"))
    })
    expect(await screen.findByText("2")).toBeTruthy()
    expect(LIVE_MS).toBe(60_000)
    expect(liveQuery.refetchInterval).toBe(LIVE_MS)
  })

  it("says how fresh the data is", () => {
    expect(updatedText(1_000, 20_000)).toBe("Updated just now")
    expect(updatedText(0, 61_000)).toBe("Updated 1 minute ago")
    expect(updatedText(0, 5 * 60_000)).toBe("Updated 5 minutes ago")
  })
})
