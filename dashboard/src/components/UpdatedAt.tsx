import { useEffect, useState } from "react"
import { updatedText } from "@/lib/updatedText"

const TICK_MS = 15_000
export function UpdatedAt({ at }: { at: number }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MS)
    return () => window.clearInterval(timer)
  }, [])
  if (!at) return null
  return (
    <span
      className="text-xs text-muted-foreground"
      aria-live="polite"
      data-testid="updated-at"
    >
      {updatedText(at, Math.max(now, at))}
    </span>
  )
}
