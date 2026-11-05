import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MessageBubble } from "./MessageBubble"

afterEach(cleanup)

describe("MessageBubble", () => {
  it("keeps user text plain", () => {
    const { container } = render(
      <MessageBubble role="user" content="**not bold**" />,
    )
    expect(container.querySelector("strong")).toBeNull()
    expect(screen.getByText("**not bold**")).toBeTruthy()
  })

  it("shows Thinking before the first token", () => {
    render(<MessageBubble role="assistant" content="" pending />)
    expect(screen.getByRole("status").textContent).toBe("Thinking…")
  })

  it("shows the status event text while waiting", () => {
    render(
      <MessageBubble
        role="assistant"
        content=""
        status="Checking your calendar…"
        pending
      />,
    )
    expect(screen.getByRole("status").textContent).toBe(
      "Checking your calendar…",
    )
  })

  it("hides the status once text streams in", () => {
    render(<MessageBubble role="assistant" content="Hi" pending />)
    expect(screen.queryByRole("status")).toBeNull()
    expect(screen.queryByRole("button", { name: "Copy message" })).toBeNull()
  })

  it("renders sources as chips", () => {
    render(
      <MessageBubble
        role="assistant"
        content={"Answer.\n\nSources:\n- Story: https://www.example.com/a"}
      />,
    )
    const chips = screen.getByRole("list", { name: "Sources" })
    expect(chips.textContent).toBe("example.comStory")
    expect(screen.queryByText(/Sources:/)).toBeNull()
  })

  it("copies the message, regenerates and shows the time", () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    const onRegenerate = vi.fn()
    const { container } = render(
      <MessageBubble
        role="assistant"
        content="Done."
        createdAt="2026-11-06T10:00:00Z"
        onRegenerate={onRegenerate}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Copy message" }))
    expect(writeText).toHaveBeenCalledWith("Done.")
    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }))
    expect(onRegenerate).toHaveBeenCalled()
    expect(container.querySelector("time")?.getAttribute("datetime")).toBe(
      "2026-11-06T10:00:00Z",
    )
  })

  it("marks a stopped reply and has no regenerate without a handler", () => {
    render(<MessageBubble role="assistant" content="Half" stopped />)
    expect(screen.getByText("Stopped")).toBeTruthy()
    expect(screen.queryByRole("button", { name: "Regenerate" })).toBeNull()
  })

  it("fades streamed words in and shows the typing dots before the first token", () => {
    const { container, rerender } = render(
      <MessageBubble role="assistant" content="" pending />,
    )
    expect(screen.getByTestId("typing-indicator")).toBeTruthy()
    rerender(<MessageBubble role="assistant" content="Hello there" pending />)
    expect(container.querySelectorAll(".stream-word")).toHaveLength(2)
    expect(container.querySelector(".animate-enter")).toBeTruthy()
    rerender(
      <MessageBubble
        role="assistant"
        content="Hello there"
        createdAt="2026-11-06T10:00:00Z"
      />,
    )
    expect(container.querySelectorAll(".stream-word")).toHaveLength(0)
    expect(container.querySelector(".animate-enter")).toBeNull()
  })
})
