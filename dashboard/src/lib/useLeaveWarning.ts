import { useEffect } from "react"

export const LEAVE_WARNING =
  "You have unsaved changes. Leave without saving them?"

export function useLeaveWarning(active: boolean) {
  useEffect(() => {
    if (!active) return
    const onUnload = (event: BeforeUnloadEvent) => event.preventDefault()
    const onClick = (event: MouseEvent) => {
      const link = (event.target as Element | null)?.closest?.("a[href]")
      if (!link || link.getAttribute("target") === "_blank") return
      if (window.confirm(LEAVE_WARNING)) return
      event.preventDefault()
      event.stopPropagation()
    }
    window.addEventListener("beforeunload", onUnload)
    document.addEventListener("click", onClick, true)
    return () => {
      window.removeEventListener("beforeunload", onUnload)
      document.removeEventListener("click", onClick, true)
    }
  }, [active])
}
