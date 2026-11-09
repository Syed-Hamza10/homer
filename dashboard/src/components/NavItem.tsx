import type { LucideIcon } from "lucide-react"
import { NavLink } from "react-router"
import { cn } from "@/lib/utils"

type Props = {
  to: string
  label: string
  icon: LucideIcon
  collapsed: boolean
  onNavigate?: () => void
}

export function NavItem({
  to,
  label,
  icon: Icon,
  collapsed,
  onNavigate,
}: Props) {
  return (
    <li>
      <NavLink
        to={to}
        end
        title={collapsed ? label : undefined}
        onClick={onNavigate}
        className={({ isActive }) =>
          cn(
            "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm text-sidebar-foreground/75 transition-colors outline-none hover:bg-sidebar-accent/70 hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
            collapsed && "justify-center px-0",
            isActive &&
              "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
          )
        }
      >
        {({ isActive }) => (
          <>
            <Icon
              aria-hidden
              className={cn("size-4 shrink-0", isActive && "text-brand")}
              strokeWidth={1.7}
            />
            <span className={cn(collapsed && "sr-only")}>{label}</span>
          </>
        )}
      </NavLink>
    </li>
  )
}
