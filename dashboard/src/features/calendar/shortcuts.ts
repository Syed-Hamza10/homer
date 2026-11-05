import type { Shortcut } from "@/components/ShortcutsHelp"

export const calendarShortcuts: Shortcut[] = [
  { keys: "t", label: "Go to today" },
  { keys: "d / w / m", label: "Day, week or month view" },
  { keys: "j / →", label: "Next period" },
  { keys: "k / ←", label: "Previous period" },
  { keys: "c", label: "New event at the next full hour" },
  { keys: "?", label: "Show these shortcuts" },
]
