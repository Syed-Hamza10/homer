import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ApiError, RECONNECT_DETAIL } from "@/lib/api"
import { ErrorNotice } from "./ErrorNotice"

afterEach(cleanup)

function show(error: Error | string, onRetry = vi.fn()) {
  render(
    <MemoryRouter>
      <ErrorNotice error={error} onRetry={onRetry} />
    </MemoryRouter>,
  )
  return onRetry
}

describe("ErrorNotice", () => {
  it("offers Try again for a plain failure", () => {
    const onRetry = show(new ApiError(500))
    fireEvent.click(screen.getByRole("button", { name: "Try again" }))
    expect(onRetry).toHaveBeenCalled()
  })

  it("offers Sign in, not Try again, on 401", () => {
    show(new ApiError(401))
    expect(screen.getByRole("link", { name: "Sign in" })).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull()
  })

  it("offers Reconnect Google when Google refused the token", () => {
    show(new ApiError(502, RECONNECT_DETAIL))
    expect(
      screen
        .getByRole("link", { name: "Reconnect Google" })
        .getAttribute("href"),
    ).toBe("/settings")
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy()
  })

  it("shows nothing without an error", () => {
    const { container } = render(<ErrorNotice error={null} />)
    expect(container.textContent).toBe("")
  })
})
