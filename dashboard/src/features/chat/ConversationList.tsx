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
    <aside className="flex w-64 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="p-3">
        <Button
          variant="outline"
          className="w-full"
          onClick={() => onSelect(null)}
        >
          New chat
        </Button>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <ul className="flex flex-col gap-1 px-3 pb-3">
          {data.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => onSelect(c.id)}
                className={cn(
                  "w-full truncate rounded-md px-3 py-2 text-left text-sm hover:bg-sidebar-accent",
                  c.id === selectedId && "bg-sidebar-accent font-medium",
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
