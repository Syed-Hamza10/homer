import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { InboxPage } from "./InboxPage"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const summary = (id: string, subject: string) => ({
  id,
  subject,
  sender: "Maya <maya@example.test>",
  to: "me@example.test",
  senders: [],
  snippet: "",
  received_at: "2026-11-05T10:00:00Z",
  message_count: 1,
  unread: false,
  starred: false,
  has_attachment: false,
  labels: ["INBOX"],
})

function thread(id: string) {
  return {
    id,
    subject: `Subject ${id}`,
    messages: [
      {
        id: `m-${id}`,
        sender: "Maya <maya@example.test>",
        to: "me@example.test",
        cc: "",
        date: "",
        received_at: null,
        labels: ["INBOX"],
        unread: false,
        body_text: `Body of ${id}`,
        body_html: null,
        remote_images: 0,
        attachments: [],
      },
    ],
  }
}

function stubApi(posts: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posts.push(`${url} ${String(init.body)}`)
        return new Response(JSON.stringify({ id: "t1", labels: [] }))
      }
      if (url.startsWith("/api/settings"))
        return new Response(JSON.stringify({ timezone: "UTC" }))
      if (url === "/api/mail/folders") return new Response("[]")
      if (url.startsWith("/api/mail/threads?"))
        return new Response(
          JSON.stringify({
            threads: [summary("t1", "First"), summary("t2", "Second")],
            next_page_token: null,
          }),
        )
      const id = url.split("/").pop()!.split("?")[0]
      return new Response(JSON.stringify(thread(id)))
    }),
  )
}

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <InboxPage />
    </QueryClientProvider>,
  )
}

describe("InboxPage shortcuts", () => {
  it("moves with j/k, opens with Enter, archives with e, and shows help on ?", async () => {
    const posts: string[] = []
    stubApi(posts)
    renderPage()
    await screen.findByText("First")
    fireEvent.keyDown(window, { key: "j" })
    fireEvent.keyDown(window, { key: "j" })
    expect(screen.getByTestId("thread-t2").dataset.focused).toBe("true")
    fireEvent.keyDown(window, { key: "k" })
    fireEvent.keyDown(window, { key: "Enter" })
    expect(await screen.findByText("Body of t1")).toBeTruthy()
    fireEvent.keyDown(window, { key: "j" })
    expect(await screen.findByText("Body of t2")).toBeTruthy()
    fireEvent.keyDown(window, { key: "e" })
    await waitFor(() =>
      expect(posts).toContain(
        '/api/mail/threads/t2/labels {"add":[],"remove":["INBOX"]}',
      ),
    )
    fireEvent.keyDown(window, { key: "?" })
    expect(
      screen.getByRole("dialog", { name: "Inbox keyboard shortcuts" }),
    ).toBeTruthy()
    fireEvent.keyDown(window, { key: "Escape" })
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("focuses search on / and ignores keys typed there", async () => {
    stubApi([])
    renderPage()
    await screen.findByText("First")
    fireEvent.keyDown(window, { key: "/" })
    const search = screen.getByLabelText("Search mail")
    expect(document.activeElement).toBe(search)
    fireEvent.keyDown(search, { key: "j" })
    expect(screen.getByTestId("thread-t1").dataset.focused).toBeUndefined()
  })
})
