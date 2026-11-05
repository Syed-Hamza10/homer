import {
  Calendar,
  Inbox,
  Landmark,
  Lock,
  MessageSquare,
  Settings,
  ShieldCheck,
  Sun,
} from "lucide-react"
import { Link, NavLink, Outlet } from "react-router"
import { cn } from "@/lib/utils"

const pages = [
  { to: "/", label: "Chat", icon: MessageSquare },
  { to: "/today", label: "Today", icon: Sun },
  { to: "/inbox", label: "Inbox", icon: Inbox },
  { to: "/calendar", label: "Calendar", icon: Calendar },
  { to: "/approvals", label: "Approvals", icon: ShieldCheck },
  { to: "/privacy", label: "Privacy", icon: Lock },
  { to: "/settings", label: "Settings", icon: Settings },
]

export function AppShell() {
  return (
    <div className="flex h-screen overflow-hidden">
      <nav className="flex w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar/95 text-sidebar-foreground backdrop-blur">
        <div className="flex items-center gap-3 border-b border-sidebar-border px-5 py-5">
          <span className="flex size-9 items-center justify-center rounded-md border border-sidebar-border bg-card text-sidebar-primary shadow-[inset_0_1px_0_var(--marble-1)]">
            <Landmark className="size-4" strokeWidth={1.5} />
          </span>
          <span className="flex flex-col leading-none">
            <span className="font-heading text-[1.35rem] tracking-[0.16em] uppercase">
              Homer
            </span>
            <span className="mt-1.5 text-[8px] font-medium tracking-[0.16em] uppercase text-muted-foreground">
              Your AI assistant at home
            </span>
          </span>
        </div>
        <div className="flex flex-1 flex-col gap-1 overflow-y-auto px-3 py-4">
          <p className="px-3 pb-2 text-[9px] font-medium tracking-[0.32em] uppercase text-muted-foreground">
            Navigation
          </p>
          {pages.map((page) => {
            const Icon = page.icon
            return (
              <NavLink
                key={page.to}
                to={page.to}
                end
                className={({ isActive }) =>
                  cn(
                    "group flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                    isActive &&
                      "bg-sidebar-accent font-medium text-sidebar-accent-foreground shadow-[inset_2px_0_0_var(--sidebar-ring)]",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon
                      className={cn(
                        "size-4 shrink-0",
                        !isActive && "opacity-60",
                      )}
                      strokeWidth={1.6}
                    />
                    <span>{page.label}</span>
                  </>
                )}
              </NavLink>
            )
          })}
        </div>
        <div className="border-t border-sidebar-border px-5 py-4">
          <p className="text-[9px] font-medium tracking-[0.26em] uppercase text-muted-foreground">
            Private by design
          </p>
          <Link
            to="/privacy"
            className="mt-1.5 block font-heading text-sm text-muted-foreground italic hover:text-foreground"
          >
            AI runs on this machine.
          </Link>
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 bg-background/40">
        <Outlet />
      </div>
    </div>
  )
}
