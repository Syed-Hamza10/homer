import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { ACTIVITY_OPEN_KEY, ActivityLine } from "./ActivityLine"
import type { ToolStep } from "./activity"

afterEach(cleanup)
beforeEach(() => localStorage.clear())

const steps: ToolStep[] = [
  {
    name: "web_search",
    args: { query: "is it raining" },
    summary:
      '{"results": [{"title": "<untrusted>Rain</untrusted>", "snippet": "<untrusted>Wet',
  },
  {
    name: "fetch_page",
    args: { url: "https://www.bbc.com/weather" },
    summary: '{"error": "timeout"}',
  },
]

describe("ActivityLine", () => {
  it("is collapsed by default and remembers when opened", () => {
    render(
      <ActivityLine steps={steps} running={false} status={null} sources={1} />,
    )
    const toggle = screen.getByRole("button", {
      name: "Searched the web · 1 source",
    })
    expect(toggle.getAttribute("aria-expanded")).toBe("false")
    expect(screen.queryByRole("list")).toBeNull()

    fireEvent.click(toggle)
    expect(toggle.getAttribute("aria-expanded")).toBe("true")
    expect(localStorage.getItem(ACTIVITY_OPEN_KEY)).toBe("1")
    const rows = screen.getAllByRole("listitem").map((row) => row.textContent)
    expect(rows).toEqual([
      "Searched the webis it raining",
      "Couldn't reach bbc.com",
    ])
    expect(document.body.textContent).not.toMatch(/untrusted|Wet|\{/)

    fireEvent.click(toggle)
    expect(screen.queryByRole("list")).toBeNull()
    expect(localStorage.getItem(ACTIVITY_OPEN_KEY)).toBe("0")
  })

  it("opens straight away when the user left it open", () => {
    localStorage.setItem(ACTIVITY_OPEN_KEY, "1")
    render(
      <ActivityLine steps={steps} running={false} status={null} sources={0} />,
    )
    expect(screen.getByRole("list", { name: "Tool activity" })).toBeTruthy()
  })

  it("updates the one line in place while running", () => {
    const search = { name: "web_search", args: { query: "q" } }
    const { rerender } = render(
      <ActivityLine steps={[search]} running status={null} sources={0} />,
    )
    expect(screen.getAllByTestId("activity")).toHaveLength(1)
    expect(screen.getByRole("button").textContent).toBe("Searching the web…")
    const pages = [
      { ...search, summary: "{}" },
      { name: "fetch_page", args: { url: "https://a.test" } },
      { name: "fetch_page", args: { url: "https://b.test" } },
    ]
    rerender(<ActivityLine steps={pages} running status={null} sources={0} />)
    expect(screen.getAllByTestId("activity")).toHaveLength(1)
    expect(screen.getByRole("button").textContent).toBe("Reading 2 pages…")
    rerender(
      <ActivityLine
        steps={pages.map((step) => ({ ...step, summary: "{}" }))}
        running={false}
        status={null}
        sources={2}
      />,
    )
    expect(screen.getByRole("button").textContent).toBe(
      "Searched the web · 2 sources",
    )
  })
})
