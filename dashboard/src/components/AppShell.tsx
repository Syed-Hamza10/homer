import { Menu } from "lucide-react"
import { useState, type KeyboardEvent } from "react"
import { Outlet } from "react-router"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useStoredFlag } from "@/lib/useStoredFlag"
import { Sidebar } from "./Sidebar"
import { Wordmark } from "./Wordmark"

export function AppShell() {
  const [collapsed, setCollapsed] = useStoredFlag("homer.sidebar.collapsed")
  const [open, setOpen] = useState(false)
  const close = () => setOpen(false)
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") close()
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <aside
        className={cn(
          "hidden shrink-0 border-r border-sidebar-border transition-[width] duration-200 md:flex",
          collapsed ? "w-16" : "w-64",
        )}
      >
        <Sidebar
          collapsed={collapsed}
          onToggle={() => setCollapsed(!collapsed)}
        />
      </aside>
      {open && (
        <div className="fixed inset-0 z-50 md:hidden" onKeyDown={onKeyDown}>
          <div
            aria-hidden
            className="absolute inset-0 bg-foreground/25"
            onClick={close}
          />
          <aside className="animate-slide-in relative flex h-full w-72 max-w-[85vw] border-r border-sidebar-border shadow-xl">
            <Sidebar collapsed={false} onToggle={close} onNavigate={close} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col bg-background/40">
        <div className="flex items-center gap-2 border-b border-border px-3 py-2 md:hidden">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Open menu"
            onClick={() => setOpen(true)}
          >
            <Menu strokeWidth={1.7} />
          </Button>
          <Wordmark />
        </div>
        <div className="flex min-h-0 min-w-0 flex-1">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
