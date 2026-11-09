import { PageHeader } from "@/components/PageHeader"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Link } from "react-router"
import { DayCard } from "./DayCard"
import { GoogleBanner } from "./GoogleBanner"
import { TodaySkeleton } from "./TodaySkeleton"
import { healthLine } from "./healthLine"
import type { FollowUp } from "./types"
import {
  useRunBrief,
  useRunDigest,
  useSendFollowUp,
  useToday,
} from "./useToday"
import { useNow } from "./useNow"

function clock(value: string): string {
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  })
}

function SectionTitle({ children }: { children: string }) {
  return (
    <h2 className="text-[9px] font-medium tracking-[0.3em] uppercase text-muted-foreground">
      {children}
    </h2>
  )
}

function FollowUpItem({ followup }: { followup: FollowUp }) {
  const send = useSendFollowUp()
  return (
    <li
      className="flex flex-col gap-1.5 border-t border-border/70 py-2.5"
      data-testid={`followup-${followup.id}`}
    >
      <span>{followup.subject}</span>
      <span className="text-xs text-muted-foreground">
        {followup.contact} · due{" "}
        {new Date(followup.due_at).toLocaleDateString()} · {followup.status}
      </span>
      {followup.draft_preview && (
        <p className="rounded-md border border-border bg-muted/40 p-2 text-xs leading-relaxed whitespace-pre-wrap">
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
          <Link to="/approvals" className="underline underline-offset-2">
            decide on Approvals
          </Link>
        </span>
      )}
    </li>
  )
}

export function TodayPage() {
  const { data, isError, isPending } = useToday()
  const now = useNow()
  const line = healthLine(data?.health)
  const brief = useRunBrief()
  const digest = useRunDigest()

  return (
    <ScrollArea className="min-h-0 flex-1">
      <main className="mx-auto flex max-w-3xl flex-col gap-7 p-6">
        <PageHeader
          eyebrow="Daily"
          title="Today"
          description={
            data
              ? `${data.unread} unread · ${data.pending_approvals} waiting for approval`
              : isError
                ? "Could not load today. Trying again shortly."
                : "Loading"
          }
          actions={
            <>
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
            </>
          }
        />

        <GoogleBanner status={data?.google} />

        {line && (
          <p
            className="text-[10px] tracking-[0.12em] uppercase text-muted-foreground"
            data-testid="health-line"
          >
            {line}
          </p>
        )}

        {[brief.error, digest.error].filter(Boolean).map((error) => (
          <p key={String(error)} className="text-sm text-destructive">
            {error?.message}
          </p>
        ))}

        {isPending && <TodaySkeleton />}

        {data && <DayCard card={data.card} now={now} />}

        {data && (
          <div className="grid gap-4 md:grid-cols-2">
            <Card size="sm">
              <CardHeader>
                <CardTitle>Brief</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed whitespace-pre-wrap text-muted-foreground">
                  {data?.brief?.content ?? "No brief yet. Generate one above."}
                </p>
              </CardContent>
            </Card>

            <Card size="sm">
              <CardHeader>
                <CardTitle>End-of-day digest</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed whitespace-pre-wrap text-muted-foreground">
                  {data?.digest?.content ?? "No digest yet."}
                </p>
              </CardContent>
            </Card>
          </div>
        )}

        <section className="flex flex-col gap-2">
          <SectionTitle>Calendar</SectionTitle>
          {data?.events.length ? (
            <ul className="flex flex-col text-sm">
              {data.events.map((event) => (
                <li
                  key={event.event_id}
                  className="flex gap-3 border-t border-border/70 py-2.5"
                >
                  <span className="w-16 shrink-0 text-muted-foreground tabular-nums">
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
          <SectionTitle>Reminders</SectionTitle>
          {data?.reminders.length ? (
            <ul className="flex flex-col text-sm">
              {data.reminders.map((reminder) => (
                <li
                  key={reminder.id}
                  className="flex gap-3 border-t border-border/70 py-2.5"
                >
                  <span className="w-16 shrink-0 text-muted-foreground tabular-nums">
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
          <SectionTitle>Follow-ups</SectionTitle>
          {data?.follow_ups.length ? (
            <ul className="flex flex-col text-sm">
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
