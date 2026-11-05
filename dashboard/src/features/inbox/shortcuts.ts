import type { Shortcut } from "@/components/ShortcutsHelp"

export const inboxShortcuts: Shortcut[] = [
  { keys: "j / k", label: "Next / previous conversation" },
  { keys: "Enter", label: "Open the highlighted conversation" },
  { keys: "u", label: "Back to the list" },
  { keys: "e", label: "Archive" },
  { keys: "s", label: "Star or unstar" },
  { keys: "r", label: "Reply" },
  { keys: "a", label: "Reply all" },
  { keys: "f", label: "Forward" },
  { keys: "Shift+I", label: "Mark as read" },
  { keys: "Shift+U", label: "Mark as unread" },
  { keys: "c", label: "New message" },
  { keys: "/", label: "Search" },
  { keys: "?", label: "Show these shortcuts" },
]
