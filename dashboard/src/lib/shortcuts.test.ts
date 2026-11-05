import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, renderHook } from "@testing-library/react"
import { handleShortcut, shortcutName, stepId, useShortcuts } from "./shortcuts"

afterEach(cleanup)

function press(key: string, init: KeyboardEventInit = {}, target?: Element) {
  const event = new KeyboardEvent("keydown", {
    key,
    bubbles: true,
    cancelable: true,
    ...init,
  })
  ;(target ?? window).dispatchEvent(event)
  return event
}

describe("shortcuts", () => {
  it("names plain, shifted and symbol keys", () => {
    expect(shortcutName(new KeyboardEvent("keydown", { key: "j" }))).toBe("j")
    expect(
      shortcutName(new KeyboardEvent("keydown", { key: "I", shiftKey: true })),
    ).toBe("Shift+I")
    expect(
      shortcutName(new KeyboardEvent("keydown", { key: "?", shiftKey: true })),
    ).toBe("?")
    expect(
      shortcutName(new KeyboardEvent("keydown", { key: "c", metaKey: true })),
    ).toBeNull()
  })

  it("runs the bound action and stops the browser default", () => {
    const archive = vi.fn()
    const event = new KeyboardEvent("keydown", { key: "e", cancelable: true })
    expect(handleShortcut(event, { e: archive })).toBe(true)
    expect(archive).toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(true)
    expect(handleShortcut(new KeyboardEvent("keydown", { key: "x" }), {})).toBe(
      false,
    )
  })

  it("ignores keys typed into fields", () => {
    const next = vi.fn()
    renderHook(() => useShortcuts({ j: next }))
    const input = document.body.appendChild(document.createElement("input"))
    press("j", {}, input)
    expect(next).not.toHaveBeenCalled()
    press("j")
    expect(next).toHaveBeenCalledTimes(1)
    input.remove()
  })
})

describe("stepId", () => {
  it("moves through a list and stops at its ends", () => {
    const ids = ["a", "b", "c"]
    expect(stepId(ids, null, 1)).toBe("a")
    expect(stepId(ids, null, -1)).toBe("c")
    expect(stepId(ids, "a", 1)).toBe("b")
    expect(stepId(ids, "c", 1)).toBe("c")
    expect(stepId(ids, "a", -1)).toBe("a")
    expect(stepId([], "a", 1)).toBeNull()
  })
})
