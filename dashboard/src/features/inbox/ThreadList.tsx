import { Search } from "lucide-react"
import { useEffect, useRef, useState, type RefObject } from "react"
import { Button } from "@/components/ui/button"
import { errorText } from "@/lib/errorText"
import { Input } from "@/components/ui/input"
import { ThreadRow } from "./ThreadRow"
import type { useThreads } from "./useMail"

type Props = {
  threads: ReturnType<typeof useThreads>
  folder: string
  query: string
  timeZone: string
  selected: string | null
  cursor: string | null
  searchRef: RefObject<HTMLInputElement | null>
  onSearch: (query: string) => void
  onOpen: (id: string, unread: boolean) => void
}

export function ThreadList({
  threads,
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
  const rows = threads.data?.pages.flatMap((page) => page.threads) ?? []

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
