import { Keyboard, PenLine } from "lucide-react"
import { useRef, useState } from "react"
import { ShortcutsHelp } from "@/components/ShortcutsHelp"
import { Button } from "@/components/ui/button"
import { errorText } from "@/lib/errorText"
import { useTimezone } from "@/features/settings/useTimezone"
import { stepId, useShortcuts } from "@/lib/shortcuts"
import { cn } from "@/lib/utils"
import { FolderList } from "./FolderList"
import { MailComposer } from "./MailComposer"
import { ReadingPane } from "./ReadingPane"
import { inboxShortcuts } from "./shortcuts"
import { ThreadList } from "./ThreadList"
import { useFolders, useLabelChange, useSortInbox, useThreads } from "./useMail"

const blankDraft = { to: "", subject: "", body: "", thread_id: null }
const fallbackFolders = [
  { id: "inbox", name: "Inbox", kind: "folder" as const, unread: 0, total: 0 },
]

export function InboxPage() {
  const timeZone = useTimezone()
  const folders = useFolders()
  const sort = useSortInbox()
  const markRead = useLabelChange()
  const [folder, setFolder] = useState("inbox")
  const [query, setQuery] = useState("")
  const [selected, setSelected] = useState<string | null>(null)
  const [composing, setComposing] = useState(false)
  const [cursor, setCursor] = useState<string | null>(null)
  const [help, setHelp] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const threads = useThreads(folder, query)
  const rows = threads.data?.pages.flatMap((page) => page.threads) ?? []
  const list = folders.data ?? fallbackFolders
  const userLabels = list
    .filter((item) => item.kind !== "folder")
    .map((item) => item.name)
  const detailOpen = selected !== null || composing
  const open = (id: string, unread: boolean) => {
    setComposing(false)
    setSelected(id)
    setCursor(id)
    if (unread) markRead.mutate({ threadId: id, remove: ["UNREAD"] })
  }
  const openId = (id: string | null) => {
    const row = rows.find((thread) => thread.id === id)
    if (row) open(row.id, row.unread)
  }
  const move = (delta: number) => {
    const next = stepId(
      rows.map((thread) => thread.id),
      cursor ?? selected,
      delta,
    )
    if (selected) openId(next)
    else setCursor(next)
  }
  const compose = () => {
    setSelected(null)
    setComposing(true)
  }

  useShortcuts(
    help
      ? {}
      : {
          j: () => move(1),
          k: () => move(-1),
          Enter: () => openId(cursor),
          u: () => {
            setSelected(null)
            setComposing(false)
          },
          c: compose,
          "/": () => searchRef.current?.focus(),
          "?": () => setHelp(true),
        },
  )

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
        <div className="flex items-baseline gap-3">
          <p className="text-[9px] font-medium tracking-[0.32em] uppercase text-muted-foreground">
            Mail
          </p>
          <h1 className="font-heading text-2xl leading-none tracking-tight">
            Inbox
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={sort.isPending}
            onClick={() => sort.mutate()}
          >
            {sort.isPending ? "Sorting…" : "Sort with Homer"}
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Keyboard shortcuts"
            onClick={() => setHelp(true)}
          >
            <Keyboard />
          </Button>
          <Button size="sm" onClick={compose}>
            <PenLine /> New message
          </Button>
        </div>
      </header>
      {(folders.error ?? sort.error) && (
        <p className="border-b border-border px-5 py-2 text-sm text-destructive">
          {errorText(folders.error ?? sort.error)}
        </p>
      )}
      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)] lg:grid-cols-[13rem_minmax(18rem,24rem)_minmax(0,1fr)]">
        <aside className="flex flex-col gap-3 border-b border-border p-3 lg:overflow-y-auto lg:border-r lg:border-b-0">
          <FolderList
            folders={list}
            selected={folder}
            onSelect={(id) => {
              setFolder(id)
              setQuery("")
              setSelected(null)
              setCursor(null)
            }}
          />
        </aside>
        <div
          className={cn(
            "min-h-0 flex-col border-border lg:flex lg:border-r",
            detailOpen ? "hidden" : "flex",
          )}
        >
          <ThreadList
            key={folder}
            threads={threads}
            folder={folder}
            query={query}
            timeZone={timeZone}
            selected={selected}
            cursor={cursor}
            searchRef={searchRef}
            onSearch={setQuery}
            onOpen={open}
          />
        </div>
        <div
          className={cn(
            "min-h-0 flex-col lg:flex",
            detailOpen ? "flex" : "hidden",
          )}
        >
          {composing ? (
            <div className="overflow-y-auto p-4">
              <MailComposer
                initial={blankDraft}
                title="New message"
                onClose={() => setComposing(false)}
              />
            </div>
          ) : selected ? (
            <ReadingPane
              key={selected}
              threadId={selected}
              timeZone={timeZone}
              userLabels={userLabels}
              shortcuts={!help}
              onClose={() => setSelected(null)}
            />
          ) : (
            <div className="hidden flex-1 items-center justify-center p-6 text-sm text-muted-foreground lg:flex">
              Choose a conversation to read it here.
            </div>
          )}
        </div>
      </div>
      {help && (
        <ShortcutsHelp
          title="Inbox"
          shortcuts={inboxShortcuts}
          onClose={() => setHelp(false)}
        />
      )}
    </main>
  )
}
