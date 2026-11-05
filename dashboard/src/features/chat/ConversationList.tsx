import { Plus, Search } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ConversationRow } from "./ConversationRow"
import { filterConversations, groupConversations } from "./groups"
import { useConversationActions } from "./useConversationActions"
import { useConversations } from "./useConversations"

type Props = {
  selectedId: string | null
  onSelect: (id: string | null) => void
}

export function ConversationList({ selectedId, onSelect }: Props) {
  const { data = [] } = useConversations()
  const { rename, remove } = useConversationActions()
  const [query, setQuery] = useState("")
  const groups = groupConversations(filterConversations(data, query))

  const onDelete = (id: string) => {
    if (id === selectedId) onSelect(null)
    remove.mutate(id)
  }

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar/60 text-sidebar-foreground">
      <div className="flex flex-col gap-2 p-3">
        <Button
          variant="outline"
          className="w-full justify-start gap-2"
          onClick={() => onSelect(null)}
        >
          <Plus className="size-3.5" strokeWidth={1.8} />
          New chat
        </Button>
        <div className="relative">
          <Search
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
            strokeWidth={1.8}
          />
          <Input
            type="search"
            aria-label="Search conversations"
            placeholder="Search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="pl-8 text-sm"
          />
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-3 px-3 pb-3">
          {groups.map((group) => (
            <section key={group.label} aria-label={group.label}>
              <p className="px-1 pb-1.5 text-[9px] font-medium tracking-[0.3em] uppercase text-muted-foreground">
                {group.label}
              </p>
              <ul className="flex flex-col gap-0.5">
                {group.items.map((c) => (
                  <li key={c.id}>
                    <ConversationRow
                      conversation={c}
                      selected={c.id === selectedId}
                      onSelect={() => onSelect(c.id)}
                      onRename={(title) => rename.mutate({ id: c.id, title })}
                      onDelete={() => onDelete(c.id)}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {query && !groups.length && (
            <p className="px-1 text-xs text-muted-foreground">No matches.</p>
          )}
        </div>
      </ScrollArea>
    </aside>
  )
}
