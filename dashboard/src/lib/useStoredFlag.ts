import { useState } from "react"

function read(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1"
  } catch {
    return false
  }
}

export function useStoredFlag(key: string) {
  const [value, setValue] = useState(() => read(key))
  const set = (next: boolean) => {
    setValue(next)
    try {
      localStorage.setItem(key, next ? "1" : "0")
    } catch {
      return
    }
  }
  return [value, set] as const
}
