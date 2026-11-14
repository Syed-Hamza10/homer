import type { KeyboardEvent } from "react"

export function composing(event: KeyboardEvent): boolean {
  return event.nativeEvent.isComposing || event.keyCode === 229
}

export function holdImeEnter(event: KeyboardEvent) {
  if (event.key === "Enter" && composing(event)) event.preventDefault()
}
