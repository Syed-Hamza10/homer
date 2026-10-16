import { describe, expect, it, vi } from "vitest"
import { createSseParser } from "./sse"

describe("createSseParser", () => {
  it("joins frames split across chunks", () => {
    const token = vi.fn()
    const parser = createSseParser({ token })
    parser.push("event: tok")
    parser.push('en\ndata: {"te')
    parser.push('xt": "hi"}\n')
    expect(token).not.toHaveBeenCalled()
    parser.push("\n")
    expect(token).toHaveBeenCalledWith({ text: "hi" })
  })

  it("handles multiple frames in one chunk", () => {
    const token = vi.fn()
    const done = vi.fn()
    const parser = createSseParser({ token, done })
    parser.push(
      'event: token\ndata: {"text": "a"}\n\nevent: token\ndata: {"text": "b"}\n\nevent: done\ndata: {"input_tokens": 1, "output_tokens": 2}\n\n',
    )
    expect(token.mock.calls).toEqual([[{ text: "a" }], [{ text: "b" }]])
    expect(done).toHaveBeenCalledWith({ input_tokens: 1, output_tokens: 2 })
  })

  it("ignores unknown events", () => {
    const token = vi.fn()
    const parser = createSseParser({ token })
    parser.push(
      'event: ping\ndata: {}\n\nevent: token\ndata: {"text": "x"}\n\n',
    )
    expect(token).toHaveBeenCalledTimes(1)
    expect(token).toHaveBeenCalledWith({ text: "x" })
  })

  it("accepts CRLF line endings", () => {
    const meta = vi.fn()
    const parser = createSseParser({ meta })
    parser.push(
      'event: meta\r\ndata: {"conversation_id": "c1", "message_id": "m1"}\r\n\r\n',
    )
    expect(meta).toHaveBeenCalledWith({
      conversation_id: "c1",
      message_id: "m1",
    })
  })
})
