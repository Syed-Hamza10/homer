import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, describe, expect, it } from "vitest"
import { ActivityLine } from "./ActivityLine"

afterEach(cleanup)

describe("ActivityLine", () => {
  it("links the reconnect event to Settings", () => {
    render(
      <MemoryRouter>
        <ActivityLine item={{ kind: "reconnect", url: "/settings" }} />
      </MemoryRouter>,
    )
    const link = screen.getByRole("link", { name: "Reconnect Google" })
    expect(link.getAttribute("href")).toBe("/settings")
  })
})
