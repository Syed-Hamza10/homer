import { NavLink, Outlet } from "react-router"
import { cn } from "@/lib/utils"

const pages = [
  { to: "/", label: "Chat" },
  { to: "/today", label: "Today" },
  { to: "/inbox", label: "Inbox" },
  { to: "/calendar", label: "Calendar" },
  { to: "/approvals", label: "Approvals" },
  { to: "/privacy", label: "Privacy" },
  { to: "/settings", label: "Settings" },
]

export function AppShell() {
  return (
    <div className="flex h-screen">
      <nav className="flex w-36 shrink-0 flex-col gap-1 border-r bg-sidebar p-3 text-sidebar-foreground">
        <p className="px-3 py-2 text-sm font-semibold">Achilles</p>
        {pages.map((page) => (
          <NavLink
            key={page.to}
            to={page.to}
            end
            className={({ isActive }) =>
              cn(
                "rounded-md px-3 py-2 text-sm hover:bg-sidebar-accent",
                isActive && "bg-sidebar-accent font-medium",
              )
            }
          >
            {page.label}
          </NavLink>
        ))}
      </nav>
      <div className="flex min-w-0 flex-1">
        <Outlet />
      </div>
    </div>
  )
}
