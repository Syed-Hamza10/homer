import { Check, Pencil, Trash2, X } from "lucide-react"
import { useState, type KeyboardEvent } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import type { Conversation } from "./types"

type Props = {
  conversation: Conversation
  selected: boolean
  onSelect: () => void
  onRename: (title: string) => void
  onDelete: () => void
}

type Mode = "view" | "rename" | "confirm"

export function ConversationRow({
  conversation,
  selected,
  onSelect,
  onRename,
  onDelete,
}: Props) {
  const title = conversation.title || "Untitled"
  const [mode, setMode] = useState<Mode>("view")
  const [value, setValue] = useState(title)

  const startRename = () => {
    setValue(title)
    setMode("rename")
  }

  const save = () => {
    const next = value.trim()
    if (next && next !== title) onRename(next)
    setMode("view")
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") save()
    if (event.key === "Escape") setMode("view")
  }

  if (mode === "rename")
    return (
      <Input
        autoFocus
        aria-label="Conversation title"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        onBlur={save}
        className="h-8 text-sm"
      />
    )

  if (mode === "confirm")
    return (
      <div className="flex items-center gap-1 rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1 text-xs">
        <span className="flex-1 truncate text-destructive">Delete chat?</span>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Confirm delete"
          onClick={() => {
            setMode("view")
            onDelete()
          }}
        >
          <Check strokeWidth={1.8} />
        </Button>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Cancel delete"
          onClick={() => setMode("view")}
        >
          <X strokeWidth={1.8} />
        </Button>
      </div>
    )

  return (
    <div
      className={cn(
        "group/row relative flex items-center rounded-md border border-transparent text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
        selected &&
          "border-border bg-card font-medium text-foreground shadow-[inset_2px_0_0_var(--sidebar-ring)]",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        onDoubleClick={startRename}
        className="min-w-0 flex-1 truncate px-3 py-2 text-left outline-none"
      >
        {title}
      </button>
      <div className="flex shrink-0 gap-0.5 pr-1 opacity-0 transition-opacity group-focus-within/row:opacity-100 group-hover/row:opacity-100">
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Rename"
          onClick={startRename}
        >
          <Pencil strokeWidth={1.8} />
        </Button>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Delete"
          onClick={() => setMode("confirm")}
        >
          <Trash2 strokeWidth={1.8} />
        </Button>
      </div>
    </div>
  )
}
