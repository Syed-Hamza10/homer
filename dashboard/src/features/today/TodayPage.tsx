import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Link } from "react-router"
import type { FollowUp, Health } from "./types"
import {
  useRunBrief,
  useRunDigest,
  useSendFollowUp,
  useToday,
} from "./useToday"

function clock(value: string): string {
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  })
}

function healthLine(health: Health | null | undefined): string {
  if (!health) return "No health check yet."
  const parts = [
    `Ollama ${health.ollama}`,
    `model ${health.model_pulled === "ok" ? "pulled" : "missing"}`,
    ...Object.entries(health.servers).map(
      ([name, status]) => `${name} ${status}`,
    ),
  ]
  if (health.self_email === "mismatch") parts.push("email-to-self paused")
  return `${parts.join(" · ")} · checked ${clock(health.checked_at)}`
}

function FollowUpItem({ followup }: { followup: FollowUp }) {
  const send = useSendFollowUp()
  return (
    <li
      className="flex flex-col gap-1 border-t py-2"
      data-testid={`followup-${followup.id}`}
    >
      <span>{followup.subject}</span>
      <span className="text-xs text-muted-foreground">
        {followup.contact} · due{" "}
        {new Date(followup.due_at).toLocaleDateString()} · {followup.status}
      </span>
      {followup.draft_preview && (
        <p className="rounded-md bg-muted p-2 text-xs whitespace-pre-wrap">
          {followup.draft_preview}
        </p>
      )}
      {followup.draft_id && !send.data && (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={send.isPending}
            onClick={() => send.mutate(followup.id)}
          >
            Send
          </Button>
          {send.error && (
            <span className="text-xs text-destructive">
              {send.error.message}
            </span>
          )}
        </div>
      )}
      {send.data && (
        <span className="text-xs text-muted-foreground">
          Approval #{send.data.id} requested ·{" "}
          <Link to="/approvals" className="underline">
            decide on Approvals
          </Link>
        </span>
      )}
    </li>
  )
}

export function TodayPage() {
  const { data } = useToday()
  const brief = useRunBrief()
  const digest = useRunDigest()

  return (
    <ScrollArea className="min-h-0 flex-1">
      <main className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
        <section className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold">Today</h1>
            <p className="text-sm text-muted-foreground">
              {data
                ? `${data.unread} unread · ${data.pending_approvals} waiting for approval`
                : "Loading"}
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={brief.isPending}
              onClick={() => brief.mutate()}
            >
              Morning brief
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={digest.isPending}
              onClick={() => digest.mutate()}
            >
              End-of-day digest
            </Button>
          </div>
        </section>

        <p className="text-xs text-muted-foreground" data-testid="health-line">
          {healthLine(data?.health)}
        </p>

        {[brief.error, digest.error].filter(Boolean).map((error) => (
          <p key={String(error)} className="text-sm text-destructive">
            {error?.message}
          </p>
        ))}

        <Card size="sm">
          <CardHeader>
            <CardTitle>Morning brief</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap text-muted-foreground">
              {data?.brief?.content ?? "No brief yet. Generate one above."}
            </p>
          </CardContent>
        </Card>

        <Card size="sm">
          <CardHeader>
            <CardTitle>End-of-day digest</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-wrap text-muted-foreground">
              {data?.digest?.content ?? "No digest yet."}
            </p>
          </CardContent>
        </Card>

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">Calendar</h2>
          {data?.events.length ? (
            <ul className="flex flex-col gap-1 text-sm">
              {data.events.map((event) => (
                <li key={event.event_id} className="flex gap-3 border-t py-2">
                  <span className="w-16 text-muted-foreground">
                    {clock(event.start)}
                  </span>
                  <span>{event.title}</span>
                  {event.location && (
                    <span className="text-muted-foreground">
                      · {event.location}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Nothing today.</p>
          )}
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">Reminders</h2>
          {data?.reminders.length ? (
            <ul className="flex flex-col gap-1 text-sm">
              {data.reminders.map((reminder) => (
                <li key={reminder.id} className="flex gap-3 border-t py-2">
                  <span className="w-16 text-muted-foreground">
                    {clock(reminder.due_at)}
                  </span>
                  <span>{reminder.text}</span>
                  <span className="text-muted-foreground">
                    · {reminder.status}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No reminders due.</p>
          )}
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">Follow-ups</h2>
          {data?.follow_ups.length ? (
            <ul className="flex flex-col gap-1 text-sm">
              {data.follow_ups.map((followup) => (
                <FollowUpItem key={followup.id} followup={followup} />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No follow-ups due.</p>
          )}
        </section>
      </main>
    </ScrollArea>
  )
}
