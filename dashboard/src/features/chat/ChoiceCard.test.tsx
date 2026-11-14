import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ChoiceCard } from "./ChoiceCard"
import type { ChoiceEvent } from "./types"

afterEach(cleanup)

const card: ChoiceEvent = {
  question_id: "q1",
  prompt: "Which Sam do you mean?",
  options: [
    { id: "a", label: "Sam Lee", detail: "sam.lee@example.test · Contact" },
    {
      id: "b",
      label: "Sam Ruiz",
      detail: "sam.ruiz@example.test · You emailed them 3 days ago",
    },
  ],
  allow_other: true,
  answered: null,
}

function show(props: Partial<Parameters<typeof ChoiceCard>[0]> = {}) {
  const onPick = vi.fn()
  const onOther = vi.fn()
  render(
    <ChoiceCard
      card={card}
      active
      onPick={onPick}
      onOther={onOther}
      {...props}
    />,
  )
  return { onPick, onOther }
}

const row = (name: RegExp) => screen.getByRole("button", { name })

describe("ChoiceCard", () => {
  it("shows one row per option with its name and detail line", () => {
    show()
    expect(row(/Sam Lee/).textContent).toContain(
      "sam.lee@example.test · Contact",
    )
    expect(row(/Sam Ruiz/).textContent).toContain("You emailed them 3 days ago")
    expect(row(/Someone else/)).toBeTruthy()
  })

  it("picks an option on click and then shows it answered", () => {
    const { onPick } = show()
    fireEvent.click(row(/Sam Ruiz/))
    expect(onPick).toHaveBeenCalledExactlyOnceWith(card.options[1])
    expect(row(/Sam Ruiz/).getAttribute("aria-pressed")).toBe("true")
    expect((row(/Sam Lee/) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.queryByRole("button", { name: /Someone else/ })).toBeNull()
    fireEvent.click(row(/Sam Lee/))
    expect(onPick).toHaveBeenCalledTimes(1)
  })

  it("picks with the number keys, but not while typing", () => {
    const { onPick } = show()
    const box = document.createElement("textarea")
    document.body.append(box)
    fireEvent.keyDown(box, { key: "1" })
    expect(onPick).not.toHaveBeenCalled()
    fireEvent.keyDown(window, { key: "3" })
    expect(onPick).not.toHaveBeenCalled()
    fireEvent.keyDown(window, { key: "2" })
    expect(onPick).toHaveBeenCalledExactlyOnceWith(card.options[1])
    fireEvent.keyDown(window, { key: "1" })
    expect(onPick).toHaveBeenCalledTimes(1)
    box.remove()
  })

  it("focuses the composer for someone else", () => {
    const { onOther, onPick } = show()
    fireEvent.click(row(/Someone else/))
    expect(onOther).toHaveBeenCalledOnce()
    expect(onPick).not.toHaveBeenCalled()
  })

  it("shows a stored answer after a reload", () => {
    const { onPick } = show({ card: { ...card, answered: "a" } })
    expect(row(/Sam Lee/).getAttribute("aria-pressed")).toBe("true")
    expect((row(/Sam Ruiz/) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.keyDown(window, { key: "2" })
    expect(onPick).not.toHaveBeenCalled()
  })

  it("cannot be picked once the chat has moved on", () => {
    const { onPick } = show({ active: false })
    expect((row(/Sam Lee/) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.keyDown(window, { key: "1" })
    expect(onPick).not.toHaveBeenCalled()
  })
})
