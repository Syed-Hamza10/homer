import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router"
import { afterEach, describe, expect, it, vi } from "vitest"
import { InboxPage } from "./InboxPage"
import type { ThreadSummary } from "./types"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
})

const summary = (
  id: string,
  subject: string,
  extra: Partial<ThreadSummary> = {},
): ThreadSummary => ({
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
  ...extra,
})

const twoThreads = [summary("t1", "First"), summary("t2", "Second")]

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

function stubApi(posts: string[], threads = twoThreads) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posts.push(`${url} ${String(init.body)}`)
      return new Response(JSON.stringify({ id: "t1", labels: [] }))
    }
    if (url.startsWith("/api/settings"))
      return new Response(JSON.stringify({ timezone: "UTC" }))
    if (url === "/api/mail/folders") return new Response("[]")
    if (url.startsWith("/api/mail/threads?"))
      return new Response(JSON.stringify({ threads, next_page_token: null }))
    const id = url.split("/").pop()!.split("?")[0]
    return new Response(JSON.stringify(thread(id)))
  })
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

function Where() {
  const location = useLocation()
  return <output data-testid="where">{location.search}</output>
}

function renderPage(entry = "/inbox") {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route
            path="/inbox"
            element={
              <>
                <InboxPage />
                <Where />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const order = () =>
  screen.getAllByTestId(/^thread-/).map((row) => row.dataset.testid)

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

describe("InboxPage URL and sorting", () => {
  it("restores the folder and the open thread from the URL", async () => {
    const fetchMock = stubApi([])
    renderPage("/inbox?folder=sent&thread=t2")
    expect(await screen.findByText("Body of t2")).toBeTruthy()
    const urls = fetchMock.mock.calls.map(([url]) => String(url))
    expect(urls.some((url) => url.includes("folder=sent"))).toBe(true)
    fireEvent.click(await screen.findByTestId("thread-t1"))
    await waitFor(() =>
      expect(screen.getByTestId("where").textContent).toBe(
        "?folder=sent&thread=t1",
      ),
    )
  })

  it("sorts by a clicked column, flips it, and puts unread first", async () => {
    stubApi(
      [],
      [
        summary("a", "Banana", {
          sender: "Cara <cara@example.test>",
          received_at: "2026-11-05T10:00:00Z",
        }),
        summary("b", "apple", {
          sender: "Ana <ana@example.test>",
          received_at: "2026-11-07T10:00:00Z",
        }),
        summary("c", "Cherry", {
          sender: "Bo <bo@example.test>",
          received_at: "2026-11-06T10:00:00Z",
          unread: true,
        }),
      ],
    )
    renderPage()
    await screen.findByText("Banana")
    expect(order()).toEqual(["thread-b", "thread-c", "thread-a"])
    expect(screen.getByTestId("sort-date").dataset.direction).toBe("desc")
    fireEvent.click(screen.getByTestId("sort-from"))
    expect(order()).toEqual(["thread-b", "thread-c", "thread-a"])
    fireEvent.click(screen.getByTestId("sort-subject"))
    expect(order()).toEqual(["thread-b", "thread-a", "thread-c"])
    fireEvent.click(screen.getByTestId("sort-subject"))
    expect(screen.getByTestId("sort-subject").dataset.direction).toBe("desc")
    expect(order()).toEqual(["thread-c", "thread-a", "thread-b"])
    fireEvent.click(screen.getByTestId("sort-from"))
    fireEvent.click(screen.getByRole("button", { name: "Unread first" }))
    expect(order()).toEqual(["thread-c", "thread-b", "thread-a"])
    expect(JSON.parse(localStorage.getItem("homer.inbox.sort.inbox")!)).toEqual(
      {
        column: "from",
        direction: "asc",
        unreadFirst: true,
      },
    )
  })
})
