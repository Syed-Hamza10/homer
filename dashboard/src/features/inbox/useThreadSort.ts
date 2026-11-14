import { useState } from "react"
import { defaultSort, type ThreadSort } from "./sortThreads"

const storageKey = (folder: string) => `homer.inbox.sort.${folder}`

function read(folder: string): ThreadSort {
  try {
    const stored = JSON.parse(
      localStorage.getItem(storageKey(folder)) ?? "null",
    ) as Partial<ThreadSort> | null
    return { ...defaultSort, ...stored }
  } catch {
    return defaultSort
  }
}

export function useThreadSort(folder: string) {
  const [chosen, setChosen] = useState<Record<string, ThreadSort>>({})
  const sort = chosen[folder] ?? read(folder)
  const set = (next: ThreadSort) => {
    setChosen((current) => ({ ...current, [folder]: next }))
    try {
      localStorage.setItem(storageKey(folder), JSON.stringify(next))
    } catch {
      return
    }
  }
  return [sort, set] as const
}
