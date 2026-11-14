import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ModelChoice } from "./ModelChoice"

afterEach(cleanup)

describe("model choice", () => {
  it("offers Quality and Fast in plain words, without parameter sizes", () => {
    const onChange = vi.fn()
    const { container } = render(
      <ModelChoice
        tiers={["supported", "degraded"]}
        value=""
        onChange={onChange}
      />,
    )
    expect(screen.getByText("Best answers; needs 16 GB")).toBeTruthy()
    expect(screen.getByText("Faster; lighter on memory")).toBeTruthy()
    expect(container.textContent).not.toMatch(/\d+B\b/)
    fireEvent.click(screen.getByRole("radio", { name: /Fast/ }))
    expect(onChange).toHaveBeenCalledWith("degraded")
  })
})
