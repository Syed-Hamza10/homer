import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import type { ReactNode } from "react"
import { MemoryRouter } from "react-router"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"
import type { Approval } from "@/features/approvals/types"
import { MessageList } from "./MessageList"
import type { ActivityItem, Message } from "./types"

afterEach(cleanup)
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

const messages: Message[] = [
  {
    id: 1,
    role: "user",
    content: "email sam",
    created_at: "2026-11-10T10:00:00",
  },
  {
    id: 2,
    role: "assistant",
    content: "Here's your email to Sam. Press Send when it looks right.",
    created_approval: true,
    created_at: "2026-11-10T10:00:05",
  },
  { id: 3, role: "user", content: "thanks", created_at: "2026-11-10T10:01:00" },
  {
    id: 4,
    role: "assistant",
    content: "Any time.",
    created_at: "2026-11-10T10:01:02",
  },
]

const approval: Approval = {
  id: 9,
  server: "google",
  action: "mail_send",
  payload: { to: "sam@example.test", subject: "Hi", body: "Body" },
  preview: "Send email to sam@example.test",
  status: "pending",
  channel: "web",
  created_at: "2026-11-10T10:00:04",
  decided_at: null,
  result: null,
  conversation_id: 1,
  message_id: 2,
}

const requested: ActivityItem = {
  kind: "approval",
  approval_id: 9,
  action: "mail_send",
  preview: approval.preview,
  payload: approval.payload,
}

function wrap(node: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("MessageList", () => {
  it("puts a stored approval right under the message that offered it", () => {
    wrap(
      <MessageList
        messages={messages}
        approvals={[approval]}
        draft={null}
        activity={[requested]}
        status={null}
        onRegenerate={vi.fn()}
      />,
    )
    expect(screen.getAllByTestId("approval-9")).toHaveLength(1)
    const card = screen.getByTestId("approval-9")
    const offered = screen.getAllByTestId("message-assistant")[0]
    const next = screen.getAllByTestId("message-user")[1]
    expect(offered.compareDocumentPosition(card)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
    expect(card.compareDocumentPosition(next)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
  })

  it("shows the live card under the streaming reply", () => {
    wrap(
      <MessageList
        messages={messages.slice(0, 1)}
        approvals={[]}
        draft={{ user: "email sam", assistant: "Here's your email to Sam." }}
        activity={[requested]}
        status={null}
        onRegenerate={vi.fn()}
      />,
    )
    const reply = screen.getByTestId("message-assistant")
    const card = screen.getByTestId("approval-9")
    expect(reply.compareDocumentPosition(card)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
  })
})
