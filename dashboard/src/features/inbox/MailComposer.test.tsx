import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MailComposer } from "./MailComposer"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const approval = {
  id: 7,
  server: "google",
  action: "mail_send",
  payload: { to: "maya@example.test", subject: "Re: Kickoff", body: "Yes" },
  preview: "Send email to maya@example.test",
  status: "pending",
  channel: "web",
  created_at: "2026-11-06T10:00:00Z",
  decided_at: null,
  result: null,
}

function renderComposer() {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <MailComposer
        title="Reply"
        initial={{
          to: "maya@example.test",
          subject: "Re: Kickoff",
          body: "\n\nOn Thu, Maya wrote:\n> Any update?",
          thread_id: "t1",
        }}
        onClose={vi.fn()}
      />
    </QueryClientProvider>,
  )
}

describe("MailComposer", () => {
  it("sends text plus the quote and shows the approval card in place", async () => {
    const fetch = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/mail/write")
        return new Response(JSON.stringify({ body: "Thursday works." }))
      expect(url).toBe("/api/mail/compose")
      expect(JSON.parse(String(init?.body))).toEqual({
        to: "maya@example.test",
        subject: "Re: Kickoff",
        body: "Thursday works.\n\nOn Thu, Maya wrote:\n> Any update?",
        thread_id: "t1",
      })
      return new Response(JSON.stringify(approval))
    })
    vi.stubGlobal("fetch", fetch)
    renderComposer()
    fireEvent.change(screen.getByLabelText("Instruction for Homer"), {
      target: { value: "say Thursday works" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Draft with Homer" }))
    expect(await screen.findByDisplayValue("Thursday works.")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Send" }))
    expect(await screen.findByTestId("approval-7")).toBeTruthy()
    expect(screen.getByText("Email to maya@example.test")).toBeTruthy()
  })
})
