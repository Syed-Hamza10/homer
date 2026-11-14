import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useDecide } from "./useDecide"

afterEach(() => vi.unstubAllGlobals())

function decided(status: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ id: 1, status }))),
  )
  const client = new QueryClient()
  const invalidate = vi.spyOn(client, "invalidateQueries")
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useDecide(), { wrapper })
  act(() => result.current.mutate({ id: 1, decision: "approve" }))
  return { result, keys: () => invalidate.mock.calls.map(([f]) => f?.queryKey) }
}

describe("useDecide", () => {
  it("refreshes calendar, mail and today once an approval has run", async () => {
    const { result, keys } = decided("done")
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(keys()).toEqual([
      ["approvals"],
      ["calendar", "events"],
      ["mail"],
      ["today"],
    ])
  })

  it("only refreshes approvals when nothing ran", async () => {
    const { result, keys } = decided("rejected")
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(keys()).toEqual([["approvals"]])
  })
})
