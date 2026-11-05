import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { SuggestedPrompts } from "./SuggestedPrompts"
import { suggestions } from "./suggestions"

afterEach(cleanup)

describe("SuggestedPrompts", () => {
  it("shows the four suggestions", () => {
    render(<SuggestedPrompts onPick={vi.fn()} />)
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(
      suggestions,
    )
  })

  it("sends the clicked suggestion", () => {
    const onPick = vi.fn()
    render(<SuggestedPrompts onPick={onPick} />)
    fireEvent.click(screen.getByText("Summarise my latest emails"))
    expect(onPick).toHaveBeenCalledWith("Summarise my latest emails")
  })
})
