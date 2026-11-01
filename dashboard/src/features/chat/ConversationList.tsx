import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { useConversations } from "./useConversations"

type Props = {
  selectedId: string | null
  onSelect: (id: string | null) => void
}

export function ConversationList({ selectedId, onSelect }: Props) {
  const { data = [] } = useConversations()
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar/60 text-sidebar-foreground">
      <div className="p-3">
        <Button
          variant="outline"
          className="w-full justify-start gap-2"
          onClick={() => onSelect(null)}
        >
          <Plus className="size-3.5" strokeWidth={1.8} />
          New chat
        </Button>
      </div>
      <p className="px-4 pb-2 text-[9px] font-medium tracking-[0.3em] uppercase text-muted-foreground">
        Conversations
      </p>
      <ScrollArea className="min-h-0 flex-1">
        <ul className="flex flex-col gap-0.5 px-3 pb-3">
          {data.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onSelect(c.id)}
                className={cn(
                  "w-full truncate rounded-md border border-transparent px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                  c.id === selectedId &&
                    "border-border bg-card font-medium text-foreground shadow-[inset_2px_0_0_var(--sidebar-ring)]",
                )}
              >
                {c.title || "Untitled"}
              </button>
            </li>
          ))}
        </ul>
      </ScrollArea>
    </aside>
  )
}
