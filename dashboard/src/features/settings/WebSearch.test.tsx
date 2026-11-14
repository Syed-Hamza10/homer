import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { WebSearch } from "./WebSearch"
import { useSaveSearch, useSearchSettings, useTestSearch } from "./useSearch"

vi.mock("./useSearch", () => ({
  useSearchSettings: vi.fn(),
  useSaveSearch: vi.fn(),
  useTestSearch: vi.fn(),
}))

afterEach(cleanup)

const idle = { mutate: vi.fn(), isPending: false }

describe("web search settings", () => {
  it("shows only the saved key's last four characters", () => {
    vi.mocked(useSearchSettings).mockReturnValue({
      data: {
        provider: "brave",
        api_provider: "brave",
        fallback: true,
        key_hint: "…abcd",
        hosts: ["api.search.brave.com"],
      },
    } as unknown as ReturnType<typeof useSearchSettings>)
    vi.mocked(useSaveSearch).mockReturnValue(
      idle as unknown as ReturnType<typeof useSaveSearch>,
    )
    vi.mocked(useTestSearch).mockReturnValue(
      idle as unknown as ReturnType<typeof useTestSearch>,
    )
    render(<WebSearch />)
    const key = screen.getByTestId("search-key") as HTMLInputElement
    expect(key.value).toBe("")
    expect(key.placeholder).toBe("Saved · …abcd")
    expect(screen.getByTestId("search-privacy").textContent).toBe(
      "Your search question goes to Brave Search. Emails and documents never do.",
    )
    expect(screen.getByRole("button", { name: "Test search" })).toBeTruthy()
  })
})
