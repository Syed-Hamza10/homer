import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { GoogleAccount } from "./GoogleAccount"
import type { GoogleStatus } from "./types"
import { useConnectGoogle, useGoogleStatus } from "./useGoogle"

vi.mock("./useGoogle", () => ({
  useGoogleStatus: vi.fn(),
  useConnectGoogle: vi.fn(),
}))

afterEach(cleanup)

const PATH = "/home/user/.homer/credentials/client_secret.json"

function show(status: Partial<GoogleStatus>) {
  vi.mocked(useGoogleStatus).mockReturnValue({
    data: {
      state: "not_connected",
      email: null,
      connected_at: null,
      days_left: null,
      connecting: false,
      client_secret_found: false,
      client_secret_path: PATH,
      ...status,
    },
  } as unknown as ReturnType<typeof useGoogleStatus>)
  vi.mocked(useConnectGoogle).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useConnectGoogle>)
  render(<GoogleAccount />)
}

describe("google account", () => {
  it("explains the setup when the client file is missing", () => {
    show({})
    expect(screen.getByText("Not connected")).toBeTruthy()
    expect(screen.getByTestId("google-setup").textContent).toContain(PATH)
    expect(
      screen.getByRole("link", { name: "the Google setup guide" }),
    ).toBeTruthy()
    expect(screen.getByRole("button", { name: "Connect" })).toBeTruthy()
  })

  it("hides the setup once the client file exists", () => {
    show({ client_secret_found: true })
    expect(screen.queryByTestId("google-setup")).toBeNull()
    expect(screen.getByRole("button", { name: "Connect" })).toBeTruthy()
  })
})
