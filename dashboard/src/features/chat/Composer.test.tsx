import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { Composer } from "./Composer"

afterEach(cleanup)

describe("Composer", () => {
  it("swaps Send for Stop while streaming", () => {
    const onStop = vi.fn()
    render(<Composer streaming onSend={vi.fn()} onStop={onStop} />)
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Stop" }))
    expect(onStop).toHaveBeenCalled()
  })
})
