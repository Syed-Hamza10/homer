import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ThreadRow } from "./ThreadRow"
import type { ThreadSummary } from "./types"

afterEach(cleanup)

const thread: ThreadSummary = {
  id: "t1",
  subject: "Invoice 2026-041",
  sender: "Tomas Keller <tomas@example.test>",
  to: "me@example.test",
  senders: [],
  snippet: "Please find the invoice",
  received_at: "2025-03-02T10:00:00Z",
  message_count: 2,
  unread: true,
  starred: true,
  has_attachment: true,
  labels: [],
}

describe("ThreadRow", () => {
  it("shows sender, subject, snippet, count and icons, bold when unread", () => {
    const onOpen = vi.fn()
    render(
      <ul>
        <ThreadRow
          thread={thread}
          timeZone="UTC"
          selected={false}
          focused={false}
          sentView={false}
          onOpen={onOpen}
        />
      </ul>,
    )
    expect(screen.getByText("Tomas Keller").className).toContain(
      "font-semibold",
    )
    expect(screen.getByText("Invoice 2026-041")).toBeTruthy()
    expect(screen.getByText("Please find the invoice")).toBeTruthy()
    expect(screen.getByLabelText("Has attachment")).toBeTruthy()
    expect(screen.getByLabelText("Starred")).toBeTruthy()
    expect(screen.getByText(/2025/)).toBeTruthy()
    fireEvent.click(screen.getByTestId("thread-t1"))
    expect(onOpen).toHaveBeenCalled()
  })

  it("names the recipient in the sent folder", () => {
    render(
      <ul>
        <ThreadRow
          thread={{ ...thread, unread: false }}
          timeZone="UTC"
          selected
          focused={false}
          sentView
          onOpen={vi.fn()}
        />
      </ul>,
    )
    expect(screen.getByText("To: me@example.test")).toBeTruthy()
  })
})
