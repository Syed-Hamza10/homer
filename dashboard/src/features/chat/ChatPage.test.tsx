import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { MemoryRouter } from "react-router"
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest"
import { ChatPage } from "./ChatPage"

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderPage() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("ChatPage", () => {
  it("keeps a message that failed to send and resends it on Try again", async () => {
    const fetch = vi.fn((url: string) =>
      url === "/api/chat"
        ? Promise.reject(new TypeError("Failed to fetch"))
        : Promise.resolve(new Response("[]")),
    )
    vi.stubGlobal("fetch", fetch)
    renderPage()
    const box = screen.getByLabelText("Message Homer") as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: "Find my flight" } })
    fireEvent.keyDown(box, { key: "Enter" })
    expect(await screen.findByText(/^Failed/)).toBeTruthy()
    expect(screen.getByTestId("message-user").textContent).toContain(
      "Find my flight",
    )
    await waitFor(() =>
      expect(
        (screen.getByLabelText("Message Homer") as HTMLTextAreaElement).value,
      ).toBe("Find my flight"),
    )
    const chats = () => fetch.mock.calls.filter(([url]) => url === "/api/chat")
    fireEvent.click(screen.getAllByRole("button", { name: "Try again" })[0])
    await waitFor(() => expect(chats()).toHaveLength(2))
  })

  it("ignores Enter while an input method is composing", () => {
    const fetch = vi.fn(() => Promise.resolve(new Response("[]")))
    vi.stubGlobal("fetch", fetch)
    renderPage()
    const box = screen.getByLabelText("Message Homer") as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: "にほん" } })
    fireEvent.keyDown(box, { key: "Enter", isComposing: true })
    fireEvent.keyDown(box, { key: "Enter", keyCode: 229 })
    expect(box.value).toBe("にほん")
    expect(fetch).not.toHaveBeenCalledWith("/api/chat", expect.anything())
  })
})
