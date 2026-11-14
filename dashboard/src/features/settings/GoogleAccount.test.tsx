import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api"
import { GoogleAccount } from "./GoogleAccount"
import type { GoogleStatus } from "./types"
import { useConnectGoogle, useGoogleStatus } from "./useGoogle"

vi.mock("./useGoogle", () => ({
  useGoogleStatus: vi.fn(),
  useConnectGoogle: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const PATH = "/home/user/.homer/credentials/client_secret.json"
const LINK = "https://accounts.google.com/o/oauth2/auth?client_id=test"

function show(status: Partial<GoogleStatus>, error: Error | null = null) {
  const refetch = vi.fn()
  const mutate = vi.fn()
  vi.mocked(useGoogleStatus).mockReturnValue({
    data: {
      state: "not_connected",
      email: null,
      connected_at: null,
      days_left: null,
      connecting: false,
      client_secret_found: false,
      client_secret_path: PATH,
      auth_url: null,
      ...status,
    },
    refetch,
  } as unknown as ReturnType<typeof useGoogleStatus>)
  vi.mocked(useConnectGoogle).mockReturnValue({
    mutate,
    isPending: false,
    error,
  } as unknown as ReturnType<typeof useConnectGoogle>)
  render(<GoogleAccount />)
  return { refetch, mutate }
}

describe("google account", () => {
  it("explains the missing OAuth client and checks again", () => {
    const { refetch } = show({})
    expect(screen.getByText("Not connected")).toBeTruthy()
    const setup = screen.getByTestId("google-setup").textContent
    expect(setup).toContain("Google OAuth client")
    expect(setup).toContain(PATH)
    expect(
      screen.getByRole("link", { name: "the Google setup guide" }),
    ).toBeTruthy()
    expect(
      screen.queryByRole("button", { name: "Sign in with Google" }),
    ).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Check again" }))
    expect(refetch).toHaveBeenCalledOnce()
  })

  it("offers sign-in once the client file exists", () => {
    const { mutate } = show({ client_secret_found: true })
    expect(screen.queryByTestId("google-setup")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Sign in with Google" }))
    expect(mutate).toHaveBeenCalledOnce()
  })

  it("shows the link to open in a private window while waiting", () => {
    show({ client_secret_found: true, connecting: true, auth_url: LINK })
    const waiting = screen.getByTestId("google-waiting").textContent
    expect(waiting).toContain(LINK)
    expect(waiting).toContain("private/incognito window")
    expect(waiting).toContain("signed into several accounts at once")
    const open = screen.getByRole("link", { name: "Open" })
    expect(open.getAttribute("href")).toBe(LINK)
    expect(open.getAttribute("target")).toBe("_blank")
    expect(
      screen.queryByRole("button", { name: "Sign in with Google" }),
    ).toBeNull()
  })

  it("copies the link", async () => {
    const writeText = vi.fn(async () => {})
    vi.stubGlobal("navigator", { clipboard: { writeText } })
    show({ client_secret_found: true, connecting: true, auth_url: LINK })
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy link" }))
    })
    expect(writeText).toHaveBeenCalledWith(LINK)
    expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy()
  })

  it("names the account once connected", () => {
    show({
      state: "connected",
      email: "tester@example.test",
      connected_at: "2026-11-10T09:00:00Z",
      days_left: 3,
      client_secret_found: true,
    })
    expect(screen.getByTestId("google-connected").textContent).toBe(
      "Connected as tester@example.test",
    )
    expect(screen.getByRole("button", { name: "Reconnect" })).toBeTruthy()
  })

  it("keeps the days left and reconnect while expiring", () => {
    show({
      state: "expiring",
      email: "tester@example.test",
      connected_at: "2026-11-08T09:00:00Z",
      days_left: 1,
      client_secret_found: true,
    })
    expect(screen.getByText("Expires in 1 day")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Reconnect" })).toBeTruthy()
  })

  it("asks to sign in again once expired", () => {
    const { mutate } = show({
      state: "expired",
      connected_at: "2026-11-01T09:00:00Z",
      days_left: 0,
      client_secret_found: true,
    })
    expect(screen.getByText("Expired")).toBeTruthy()
    expect(screen.getByTestId("google-ready").textContent).toContain(
      "Sign in again",
    )
    fireEvent.click(screen.getByRole("button", { name: "Reconnect" }))
    expect(mutate).toHaveBeenCalledOnce()
  })

  it("says plainly when sign-in could not start", () => {
    show({ client_secret_found: true }, new ApiError(409, "did not start"))
    expect(screen.getByRole("alert").textContent).toContain(
      "Google sign-in could not start",
    )
  })
})
