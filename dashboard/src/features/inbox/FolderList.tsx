import { cn } from "@/lib/utils"
import type { Folder, FolderKind } from "./types"

type Props = {
  folders: Folder[]
  selected: string
  onSelect: (id: string) => void
}

const groups: { kind: FolderKind; title: string }[] = [
  { kind: "folder", title: "Mail" },
  { kind: "category", title: "Sorted by Homer" },
  { kind: "label", title: "Labels" },
]

function count(folder: Folder): number {
  return folder.id === "drafts" ? folder.total : folder.unread
}

export function FolderList({ folders, selected, onSelect }: Props) {
  return (
    <>
      <select
        aria-label="Folder"
        value={selected}
        onChange={(event) => onSelect(event.target.value)}
        className="h-8 rounded-md border border-input bg-card/60 px-2 text-sm lg:hidden"
      >
        {folders.map((folder) => (
          <option key={folder.id} value={folder.id}>
            {folder.name}
            {count(folder) ? ` (${count(folder)})` : ""}
          </option>
        ))}
      </select>
      <nav aria-label="Folders" className="hidden flex-col gap-4 lg:flex">
        {groups.map(({ kind, title }) => {
          const members = folders.filter((folder) => folder.kind === kind)
          if (members.length === 0) return null
          return (
            <div key={kind} className="flex flex-col gap-0.5">
              <p className="px-2 pb-1 text-xs font-medium text-muted-foreground">
                {title}
              </p>
              {members.map((folder) => (
                <button
                  key={folder.id}
                  type="button"
                  aria-current={folder.id === selected ? "page" : undefined}
                  onClick={() => onSelect(folder.id)}
                  className={cn(
                    "flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground",
                    folder.id === selected &&
                      "bg-muted font-medium text-foreground shadow-[inset_2px_0_0_var(--ring)]",
                    folder.unread > 0 && "text-foreground",
                  )}
                >
                  <span className="truncate">{folder.name}</span>
                  {count(folder) > 0 && (
                    <span className="text-xs tabular-nums">
                      {count(folder)}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )
        })}
      </nav>
    </>
  )
}
