import { ArrowDown, ArrowUp, Search } from "lucide-react"
import { useEffect, useRef, useState, type RefObject } from "react"
import { UpdatedAt } from "@/components/UpdatedAt"
import { Button } from "@/components/ui/button"
import { errorText } from "@/lib/errorText"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import {
  directionText,
  nextSort,
  type SortColumn,
  type ThreadSort,
} from "./sortThreads"
import { ThreadRow } from "./ThreadRow"
import type { ThreadSummary } from "./types"
import type { useThreads } from "./useMail"

type Props = {
  threads: ReturnType<typeof useThreads>
  rows: ThreadSummary[]
  sort: ThreadSort
  onSort: (sort: ThreadSort) => void
  folder: string
  query: string
  timeZone: string
  selected: string | null
  cursor: string | null
  searchRef: RefObject<HTMLInputElement | null>
  onSearch: (query: string) => void
  onOpen: (id: string, unread: boolean) => void
}

function SortHeader({
  column,
  label,
  sort,
  onSort,
  className,
}: {
  column: SortColumn
  label: string
  sort: ThreadSort
  onSort: (sort: ThreadSort) => void
  className?: string
}) {
  const active = sort.column === column
  const Arrow = sort.direction === "asc" ? ArrowUp : ArrowDown
  return (
    <button
      type="button"
      data-testid={`sort-${column}`}
      data-direction={active ? sort.direction : undefined}
      aria-pressed={active}
      aria-label={
        active
          ? `${label}, ${directionText(column, sort.direction)}`
          : `Sort by ${label}`
      }
      onClick={() => onSort(nextSort(sort, column))}
      className={cn(
        "flex items-center gap-1 rounded-sm px-1 py-0.5 hover:text-foreground",
        active ? "font-medium text-foreground" : "text-muted-foreground",
        className,
      )}
    >
      {label}
      {active && <Arrow aria-hidden className="size-3" />}
    </button>
  )
}

export function ThreadList({
  threads,
  rows,
  sort,
  onSort,
  folder,
  query,
  timeZone,
  selected,
  cursor,
  searchRef,
  onSearch,
  onOpen,
}: Props) {
  const [draft, setDraft] = useState(query)
  const sentinel = useRef<HTMLLIElement>(null)
  const { fetchNextPage, hasNextPage, isFetchingNextPage } = threads

  useEffect(() => {
    const node = sentinel.current
    if (!node || !hasNextPage || typeof IntersectionObserver === "undefined")
      return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting) && !isFetchingNextPage)
        void fetchNextPage()
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [fetchNextPage, hasNextPage, isFetchingNextPage])

  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-label="Messages">
      <form
        role="search"
        className="flex items-center gap-2 border-b border-border px-3 py-2"
        onSubmit={(event) => {
          event.preventDefault()
          onSearch(draft.trim())
        }}
      >
        <Search className="size-4 shrink-0 text-muted-foreground" />
        <Input
          ref={searchRef}
          aria-label="Search mail"
          placeholder="Search mail, e.g. from:maya has:attachment"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        {query && (
          <Button
            size="xs"
            variant="ghost"
            type="button"
            onClick={() => {
              setDraft("")
              onSearch("")
            }}
          >
            Clear
          </Button>
        )}
      </form>
      <div className="flex items-center gap-2 border-b border-border px-3 py-1.5">
        <button
          type="button"
          aria-pressed={sort.unreadFirst}
          onClick={() => onSort({ ...sort, unreadFirst: !sort.unreadFirst })}
          className={cn(
            "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
            sort.unreadFirst
              ? "border-ring/50 bg-muted text-foreground"
              : "border-border text-muted-foreground hover:text-foreground",
          )}
        >
          Unread first
        </button>
        <span className="ml-auto">
          <UpdatedAt at={threads.dataUpdatedAt} />
        </span>
      </div>
      <div
        role="toolbar"
        aria-label="Sort messages"
        className="flex items-center gap-2 border-b border-border px-2 py-1 text-xs"
      >
        <SortHeader
          column="from"
          label={folder === "sent" ? "To" : "From"}
          sort={sort}
          onSort={onSort}
        />
        <SortHeader
          column="subject"
          label="Subject"
          sort={sort}
          onSort={onSort}
        />
        <SortHeader
          column="date"
          label="Date"
          sort={sort}
          onSort={onSort}
          className="ml-auto"
        />
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {rows.map((thread) => (
          <ThreadRow
            key={thread.id}
            thread={thread}
            timeZone={timeZone}
            selected={thread.id === selected}
            focused={thread.id === cursor}
            sentView={folder === "sent"}
            onOpen={() => onOpen(thread.id, thread.unread)}
          />
        ))}
        {threads.isPending && (
          <li className="px-3 py-6 text-sm text-muted-foreground">Loading…</li>
        )}
        {threads.error && (
          <li className="px-3 py-6 text-sm text-destructive">
            {errorText(threads.error)}
          </li>
        )}
        {!threads.isPending && !threads.error && rows.length === 0 && (
          <li className="px-3 py-6 text-sm text-muted-foreground">
            {query ? "No messages match this search." : "Nothing here."}
          </li>
        )}
        {hasNextPage && (
          <li ref={sentinel} className="flex justify-center px-3 py-3">
            <Button
              size="xs"
              variant="outline"
              disabled={isFetchingNextPage}
              onClick={() => void fetchNextPage()}
            >
              {isFetchingNextPage ? "Loading…" : "Load more"}
            </Button>
          </li>
        )}
      </ul>
    </section>
  )
}
