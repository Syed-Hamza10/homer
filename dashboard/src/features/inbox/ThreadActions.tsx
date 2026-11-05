import {
  Archive,
  Forward,
  Inbox,
  Mail,
  Reply,
  ReplyAll,
  Star,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import type { ReplyMode } from "./types"

type Props = {
  labels: string[]
  userLabels: string[]
  busy: boolean
  onReply: (mode: ReplyMode) => void
  onChange: (add: string[], remove: string[]) => void
  onMarkUnread: () => void
  onArchive: () => void
}

export function ThreadActions({
  labels,
  userLabels,
  busy,
  onReply,
  onChange,
  onMarkUnread,
  onArchive,
}: Props) {
  const starred = labels.includes("STARRED")
  const inInbox = labels.includes("INBOX")
  const addable = userLabels.filter((name) => !labels.includes(name))

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Button
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={() => onReply("reply")}
      >
        <Reply /> Reply
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={() => onReply("reply_all")}
      >
        <ReplyAll /> Reply all
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={busy}
        onClick={() => onReply("forward")}
      >
        <Forward /> Forward
      </Button>
      <span className="mx-1 h-5 w-px bg-border" aria-hidden />
      {inInbox ? (
        <Button size="sm" variant="ghost" disabled={busy} onClick={onArchive}>
          <Archive /> Archive
        </Button>
      ) : (
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() => onChange(["INBOX"], [])}
        >
          <Inbox /> Move to inbox
        </Button>
      )}
      <Button
        size="sm"
        variant="ghost"
        disabled={busy}
        aria-pressed={starred}
        onClick={() =>
          starred ? onChange([], ["STARRED"]) : onChange(["STARRED"], [])
        }
      >
        <Star className={starred ? "fill-current text-amber-500" : undefined} />
        {starred ? "Unstar" : "Star"}
      </Button>
      <Button size="sm" variant="ghost" disabled={busy} onClick={onMarkUnread}>
        <Mail /> Mark unread
      </Button>
      {addable.length > 0 && (
        <select
          aria-label="Add label"
          value=""
          disabled={busy}
          onChange={(event) => onChange([event.target.value], [])}
          className="h-7 rounded-md border border-input bg-card/60 px-2 text-xs"
        >
          <option value="">Add label…</option>
          {addable.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}
