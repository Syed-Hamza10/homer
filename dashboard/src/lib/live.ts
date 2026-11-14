import { focusManager } from "@tanstack/react-query"

export const LIVE_MS = 60_000

export const liveQuery = {
  refetchOnWindowFocus: true,
  refetchInterval: LIVE_MS,
} as const

export function refetchOnWindowFocus() {
  focusManager.setEventListener((handleFocus) => {
    const onChange = () => handleFocus()
    window.addEventListener("visibilitychange", onChange, false)
    window.addEventListener("focus", onChange, false)
    return () => {
      window.removeEventListener("visibilitychange", onChange)
      window.removeEventListener("focus", onChange)
    }
  })
}
