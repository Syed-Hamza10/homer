import {
  Calendar,
  Inbox,
  Lock,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  ShieldCheck,
  SquarePen,
  Sun,
} from "lucide-react"
import { Link, useLocation, useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { ConversationList } from "@/features/chat/ConversationList"
import { cn } from "@/lib/utils"
import { NavItem } from "./NavItem"
import { Wordmark } from "./Wordmark"

const pages = [
  { to: "/", label: "Chat", icon: MessageSquare },
  { to: "/today", label: "Today", icon: Sun },
  { to: "/inbox", label: "Inbox", icon: Inbox },
  { to: "/calendar", label: "Calendar", icon: Calendar },
  { to: "/approvals", label: "Approvals", icon: ShieldCheck },
]

const utilities = [
  { to: "/privacy", label: "Privacy", icon: Lock },
  { to: "/settings", label: "Settings", icon: Settings },
]

type Props = {
  collapsed: boolean
  onToggle: () => void
  onNavigate?: () => void
}

export function Sidebar({ collapsed, onToggle, onNavigate }: Props) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose

  const newChat = () => {
    navigate("/")
    onNavigate?.()
  }

  return (
    <nav
      aria-label="Main"
      className="flex h-full w-full flex-col bg-sidebar text-sidebar-foreground"
    >
      <div
        className={cn(
          "flex items-center gap-2 px-3 pt-4 pb-3",
          collapsed && "flex-col",
        )}
      >
        <Link
          to="/"
          onClick={onNavigate}
          aria-label="Homer, new chat"
          className="rounded-md px-1 outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
        >
          <Wordmark compact={collapsed} />
        </Link>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={onToggle}
          className={cn("text-muted-foreground", !collapsed && "ml-auto")}
        >
          <ToggleIcon strokeWidth={1.7} />
        </Button>
      </div>
      <div className="px-3 pb-3">
        <Button
          variant="outline"
          onClick={newChat}
          title={collapsed ? "New chat" : undefined}
          className={cn(
            "h-9 w-full justify-start gap-2 bg-card/70 font-normal",
            collapsed && "justify-center px-0",
          )}
        >
          <SquarePen className="size-4" strokeWidth={1.7} />
          <span className={cn(collapsed && "sr-only")}>New chat</span>
        </Button>
      </div>
      <ul className="flex flex-col gap-px px-3">
        {pages.map((page) => (
          <NavItem
            key={page.to}
            {...page}
            collapsed={collapsed}
            onNavigate={onNavigate}
          />
        ))}
      </ul>
      {pathname === "/" && !collapsed ? (
        <ConversationList onNavigate={onNavigate} />
      ) : (
        <div className="flex-1" />
      )}
      <div className="border-t border-sidebar-border px-3 py-3">
        <ul className="flex flex-col gap-px">
          {utilities.map((page) => (
            <NavItem
              key={page.to}
              {...page}
              collapsed={collapsed}
              onNavigate={onNavigate}
            />
          ))}
        </ul>
        {!collapsed && (
          <p className="px-2.5 pt-2 font-heading text-[13px] text-muted-foreground italic">
            AI runs on this machine.
          </p>
        )}
      </div>
    </nav>
  )
}
