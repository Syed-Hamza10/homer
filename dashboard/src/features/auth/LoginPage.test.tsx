import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, describe, expect, it } from "vitest"
import { LoginPage } from "./LoginPage"

function show() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("LoginPage", () => {
  afterEach(cleanup)

  it("explains what the passphrase is", () => {
    show()
    expect(
      screen.getByText(
        /This is the passphrase you chose when you installed Homer\. It only unlocks this app on this computer\./,
      ),
    ).toBeTruthy()
  })

  it("keeps the recovery steps closed until Forgot it is opened", () => {
    show()
    const details = screen
      .getByText("Forgot it?")
      .closest("details") as HTMLDetailsElement
    expect(details.open).toBe(false)
    fireEvent.click(screen.getByText("Forgot it?"))
    details.open = true
    expect(screen.getByText("homer passphrase")).toBeTruthy()
    expect(screen.getByText(/sign in with the new passphrase/)).toBeTruthy()
  })
})
