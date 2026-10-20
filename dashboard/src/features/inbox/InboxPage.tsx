import { Fragment } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Email } from "./types"
import {
  useArchive,
  useDraft,
  useFollowUp,
  useInbox,
  useRefreshInbox,
} from "./useInbox"

function InboxRow({ email }: { email: Email }) {
  const archive = useArchive(email.message_id)
  const followUp = useFollowUp(email.message_id)
  const draft = useDraft(email.message_id)
  const busy = archive.isPending || followUp.isPending || draft.isPending
  const error = archive.error ?? followUp.error ?? draft.error

  return (
    <Fragment>
      <tr className="border-t align-top">
        <td className="py-2 pr-2">
          <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs">
            {email.category}
          </span>
          {email.priority && (
            <span className="ml-1 text-xs font-medium">Priority</span>
          )}
        </td>
        <td className="max-w-40 truncate py-2 pr-2 text-muted-foreground">
          {email.sender}
        </td>
        <td className="py-2 pr-2">
          <p className={email.unread ? "font-medium" : undefined}>
            {email.subject}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            {email.snippet}
          </p>
        </td>
        <td className="py-2 pr-2 text-xs text-muted-foreground">
          {new Date(email.received_at).toLocaleDateString()}
        </td>
        <td className="py-2">
          <div className="flex justify-end gap-1">
            <Button
              size="xs"
              variant="outline"
              disabled={busy}
              onClick={() => draft.mutate()}
            >
              Draft
            </Button>
            <Button
              size="xs"
              variant="outline"
              disabled={busy}
              onClick={() => followUp.mutate()}
            >
              Follow up
            </Button>
            <Button
              size="xs"
              variant="ghost"
              disabled={busy}
              onClick={() => archive.mutate()}
            >
              Archive
            </Button>
          </div>
        </td>
      </tr>
      {error && (
        <tr>
          <td colSpan={5} className="pb-2 text-xs text-destructive">
            {error.message}
          </td>
        </tr>
      )}
      {followUp.data && (
        <tr>
          <td colSpan={5} className="pb-2 text-xs text-muted-foreground">
            Follow-up #{followUp.data.id} due{" "}
            {new Date(followUp.data.due_at).toLocaleDateString()}.
          </td>
        </tr>
      )}
      {draft.data && (
        <tr>
          <td colSpan={5} className="pb-3">
            <Card size="sm">
              <CardContent className="flex flex-col gap-1">
                <p className="text-xs text-muted-foreground">
                  Draft {draft.data.draft_id} to {draft.data.to} ·{" "}
                  {draft.data.subject}
                </p>
                <p className="text-sm whitespace-pre-wrap">{draft.data.body}</p>
              </CardContent>
            </Card>
          </td>
        </tr>
      )}
    </Fragment>
  )
}

export function InboxPage() {
  const { data: messages = [], isPending } = useInbox()
  const refresh = useRefreshInbox()

  return (
    <ScrollArea className="min-h-0 flex-1">
      <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
        <section className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold">Inbox</h1>
            <p className="text-sm text-muted-foreground">
              {messages.length} cached messages
              {refresh.data
                ? ` · ${refresh.data.labeled} labeled, ${refresh.data.failed} failed`
                : ""}
            </p>
          </div>
          <Button
            size="sm"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
          >
            Refresh &amp; triage
          </Button>
        </section>
        {refresh.error && (
          <p className="text-sm text-destructive">{refresh.error.message}</p>
        )}
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-2 font-medium">Category</th>
              <th className="py-2 font-medium">From</th>
              <th className="py-2 font-medium">Subject</th>
              <th className="py-2 font-medium">Received</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {messages.map((email) => (
              <InboxRow key={email.message_id} email={email} />
            ))}
            {!isPending && messages.length === 0 && (
              <tr className="border-t">
                <td colSpan={5} className="py-2 text-muted-foreground">
                  No messages cached yet. Refresh to load the inbox.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </main>
    </ScrollArea>
  )
}
