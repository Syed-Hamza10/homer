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
        className="h-7 text-[13px]"
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
        "group/row relative flex items-center rounded-md text-[13px] text-sidebar-foreground/75 transition-colors hover:bg-sidebar-accent/70 hover:text-sidebar-foreground",
        selected && "bg-sidebar-accent text-sidebar-accent-foreground",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        onDoubleClick={startRename}
        className="min-w-0 flex-1 truncate rounded-md px-2.5 py-1.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
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
