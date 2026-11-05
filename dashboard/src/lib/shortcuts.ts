import { useEffect, useRef } from "react"

export type Bindings = Record<string, () => void>

const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"])

export function shortcutName(event: KeyboardEvent): string | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null
  const target = event.target as HTMLElement | null
  if (target && (TYPING.has(target.tagName) || target.isContentEditable))
    return null
  if (event.shiftKey && /^[a-z]$/i.test(event.key))
    return `Shift+${event.key.toUpperCase()}`
  return event.key
}

export function handleShortcut(event: KeyboardEvent, bindings: Bindings) {
  const name = shortcutName(event)
  const action = name ? bindings[name] : undefined
  if (!action) return false
  event.preventDefault()
  action()
  return true
}

export function useShortcuts(bindings: Bindings) {
  const current = useRef(bindings)
  useEffect(() => {
    current.current = bindings
  })
  useEffect(() => {
    const listener = (event: KeyboardEvent) =>
      handleShortcut(event, current.current)
    window.addEventListener("keydown", listener)
    return () => window.removeEventListener("keydown", listener)
  }, [])
}

export function stepId(
  ids: string[],
  current: string | null,
  delta: number,
): string | null {
  if (ids.length === 0) return null
  const at = current === null ? -1 : ids.indexOf(current)
  if (at === -1) return delta > 0 ? ids[0] : ids[ids.length - 1]
  return ids[Math.min(ids.length - 1, Math.max(0, at + delta))]
}
