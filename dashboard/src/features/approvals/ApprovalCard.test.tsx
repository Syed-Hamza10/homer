import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ApprovalCard } from "./ApprovalCard"
import type { PendingApproval } from "./types"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const mail: PendingApproval = {
  id: 4,
  action: "mail_send",
  preview: "Send email to sam@example.test",
  payload: {
    draft_id: "d1",
    to: "sam@example.test",
    to_name: "Sam Rivers",
    subject: "Launch",
    body: "Hi Sam,\n\nThe launch moved to Friday.",
  },
  status: "pending",
}

function renderCard(approval: PendingApproval) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ApprovalCard approval={approval} />
    </QueryClientProvider>,
  )
}

describe("ApprovalCard", () => {
  it("reads as an email preview with one primary Send email", () => {
    renderCard(mail)
    expect(screen.getByRole("heading").textContent).toBe("Email to Sam Rivers")
    expect(screen.getByText("Launch")).toBeTruthy()
    expect(screen.getByText(/The launch moved to Friday/)).toBeTruthy()
    const send = screen.getByRole("button", { name: "Send email" })
    expect(send.dataset.variant).toBe("brand")
    expect(screen.getByRole("button", { name: "Edit" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "Discard" })).toBeTruthy()
  })

  it("swaps the buttons for a status chip once sent", async () => {
    const fetch = vi.fn(
      async () => new Response(JSON.stringify({ ...mail, status: "done" })),
    )
    vi.stubGlobal("fetch", fetch)
    renderCard(mail)
    fireEvent.click(screen.getByRole("button", { name: "Send email" }))
    expect(await screen.findByText("Sent")).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Send email" })).toBeNull()
  })

  it("shows a decided status from the server without buttons", () => {
    renderCard({ ...mail, status: "expired" })
    expect(screen.getByText("Expired")).toBeTruthy()
    expect(screen.queryByRole("button")).toBeNull()
  })
})
