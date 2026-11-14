import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useReplying } from "./streams"
import { useChatStream } from "./useChatStream"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const card = {
  question_id: "q1",
  prompt: "Which Sam do you mean?",
  options: [{ id: "a", label: "Sam Lee", detail: "Contact" }],
  allow_other: true,
  answered: null,
}

const frames = [
  `event: meta\ndata: ${JSON.stringify({ conversation_id: 4, message_id: 1 })}`,
  `event: choice\ndata: ${JSON.stringify(card)}`,
  `event: done\ndata: ${JSON.stringify({ input_tokens: 0, output_tokens: 0 })}`,
].join("\n\n")

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      {children}
    </QueryClientProvider>
  )
}

describe("useChatStream", () => {
  it("sends a picked option as a hint and keeps a streamed card", async () => {
    let body: unknown = null
    const fetch = vi.fn((_: string, init: RequestInit) => {
      body = JSON.parse(String(init.body))
      return Promise.resolve(new Response(`${frames}\n\n`))
    })
    vi.stubGlobal("fetch", fetch)
    const { result } = renderHook(() => useChatStream("4", vi.fn()), {
      wrapper,
    })
    let sent: Promise<boolean> = Promise.resolve(true)
    act(() => {
      sent = result.current.send("Sam Lee", {
        question_id: "q1",
        option_id: "a",
      })
    })
    await act(() => sent)
    expect(fetch.mock.calls[0][0]).toBe("/api/chat")
    expect(body).toEqual({
      conversation_id: "4",
      message: "Sam Lee",
      choice: { question_id: "q1", option_id: "a" },
    })
    expect(result.current.activity).toEqual([{ kind: "choice", ...card }])
  })

  it("keeps tokens in their own conversation while another one is open", async () => {
    const encoder = new TextEncoder()
    let push: (frame: string) => void = () => {}
    let finish: () => void = () => {}
    let signal: AbortSignal | undefined
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        push = (frame) => controller.enqueue(encoder.encode(`${frame}\n\n`))
        finish = () => controller.close()
      },
    })
    vi.stubGlobal(
      "fetch",
      vi.fn((_: string, init: RequestInit) => {
        signal = init.signal ?? undefined
        return Promise.resolve(new Response(body))
      }),
    )
    const { result, rerender } = renderHook(
      ({ id }) => ({
        chat: useChatStream(id, vi.fn()),
        replying: useReplying(),
      }),
      { wrapper, initialProps: { id: "8" } },
    )
    let sent: Promise<boolean> = Promise.resolve(true)
    act(() => {
      sent = result.current.chat.send("Plan my week")
    })
    const token = (text: string) =>
      act(() => push(`event: token\ndata: ${JSON.stringify({ text })}`))
    act(() =>
      push(
        `event: meta\ndata: ${JSON.stringify({ conversation_id: 8, message_id: 2 })}`,
      ),
    )
    await token("Monday ")
    await waitFor(() =>
      expect(result.current.chat.draft?.assistant).toBe("Monday "),
    )
    rerender({ id: "9" })
    await token("is busy.")
    await waitFor(() => expect(result.current.replying.has("8")).toBe(true))
    expect(result.current.chat.draft).toBeNull()
    expect(result.current.chat.streaming).toBe(false)
    expect(signal?.aborted).toBe(false)
    rerender({ id: "8" })
    await waitFor(() =>
      expect(result.current.chat.draft?.assistant).toBe("Monday is busy."),
    )
    act(() => finish())
    await act(() => sent)
    expect(result.current.replying.has("8")).toBe(false)
  })

  it("marks a message failed when the request never starts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("", { status: 500 }))),
    )
    const { result } = renderHook(() => useChatStream("12", vi.fn()), {
      wrapper,
    })
    let ok = true
    await act(async () => {
      ok = await result.current.send("Hello")
    })
    expect(ok).toBe(false)
    expect(result.current.failed).toBe("Hello")
    expect(result.current.streaming).toBe(false)
  })
})
