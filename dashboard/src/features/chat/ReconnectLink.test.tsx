import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, describe, expect, it } from "vitest"
import { ReconnectLink } from "./ReconnectLink"

afterEach(cleanup)

describe("ReconnectLink", () => {
  it("links the reconnect event to Settings", () => {
    render(
      <MemoryRouter>
        <ReconnectLink url="/settings" />
      </MemoryRouter>,
    )
    const link = screen.getByRole("link", { name: "Reconnect Google" })
    expect(link.getAttribute("href")).toBe("/settings")
  })
})
