import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
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
    let sent: Promise<void> = Promise.resolve()
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
})
