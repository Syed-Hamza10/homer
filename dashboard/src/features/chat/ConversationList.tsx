import { Search, X } from "lucide-react"
import { useState, type KeyboardEvent } from "react"
import { useNavigate, useSearchParams } from "react-router"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { ConversationRow } from "./ConversationRow"
import { filterConversations, groupConversations } from "./groups"
import { useReplying } from "./streams"
import { useConversationActions } from "./useConversationActions"
import { useConversations } from "./useConversations"

type Props = { onNavigate?: () => void }

export function ConversationList({ onNavigate }: Props) {
  const { data = [], isPending } = useConversations()
  const { rename, remove } = useConversationActions()
  const replying = useReplying()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const selectedId = params.get("conversation")
  const [searching, setSearching] = useState(false)
  const [query, setQuery] = useState("")
  const groups = groupConversations(filterConversations(data, query))

  const select = (id: string | null) => {
    navigate(id ? `/?conversation=${id}` : "/")
    onNavigate?.()
  }

  const onDelete = (id: number) => {
    if (String(id) === selectedId) select(null)
    remove.mutate(id)
  }

  const closeSearch = () => {
    setQuery("")
    setSearching(false)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") closeSearch()
  }

  return (
    <section
      aria-label="Recent chats"
      className="flex min-h-0 flex-1 flex-col pt-4"
    >
      <div className="flex h-8 items-center gap-1 pr-3 pl-5">
        {searching ? (
          <>
            <Input
              autoFocus
              type="search"
              aria-label="Search conversations"
              placeholder="Search chats"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={onKeyDown}
              onBlur={() => !query && setSearching(false)}
              className="h-7 text-[13px]"
            />
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Close search"
              onClick={closeSearch}
            >
              <X strokeWidth={1.8} />
            </Button>
          </>
        ) : (
          <>
            <h2 className="flex-1 font-sans text-xs font-medium text-muted-foreground">
              Recent
            </h2>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Search conversations"
              title="Search chats"
              onClick={() => setSearching(true)}
              className="text-muted-foreground"
            >
              <Search strokeWidth={1.8} />
            </Button>
          </>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-3 px-3 pt-1 pb-3">
          {isPending &&
            [0, 1, 2, 3].map((index) => (
              <Skeleton key={index} className="h-7 w-full" />
            ))}
          {groups.map((group) => (
            <section key={group.label} aria-label={group.label}>
              <h3 className="px-2.5 pb-1 font-sans text-[11px] text-muted-foreground/90">
                {group.label}
              </h3>
              <ul className="flex flex-col gap-px">
                {group.items.map((c) => (
                  <li key={c.id}>
                    <ConversationRow
                      conversation={c}
                      selected={String(c.id) === selectedId}
                      replying={replying.has(String(c.id))}
                      onSelect={() => select(String(c.id))}
                      onRename={(title) => rename.mutate({ id: c.id, title })}
                      onDelete={() => onDelete(c.id)}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {query && !groups.length && (
            <p className="px-2.5 text-xs text-muted-foreground">No matches.</p>
          )}
          {!isPending && !query && !data.length && (
            <p className="px-2.5 text-xs leading-relaxed text-muted-foreground">
              Your chats will show up here.
            </p>
          )}
        </div>
      </div>
    </section>
  )
}
