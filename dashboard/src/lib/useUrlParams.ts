import { useSearchParams } from "react-router"

export type ParamChanges = Record<string, string | null>

export function useUrlParams() {
  const [params, setParams] = useSearchParams()
  const update = (changes: ParamChanges, replace = false) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value)
          else next.delete(key)
        }
        return next
      },
      { replace },
    )
  return [params, update] as const
}
