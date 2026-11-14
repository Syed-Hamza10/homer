import { PageHeader } from "@/components/PageHeader"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Link } from "react-router"
import { BriefPanel } from "./BriefPanel"
import { DayCard } from "./DayCard"
import { clockTime } from "./dayFormat"
import { GoogleBanner } from "./GoogleBanner"
import { TodaySkeleton } from "./TodaySkeleton"
import { healthLine } from "./healthLine"
import type { FollowUp } from "./types"
import { useSendFollowUp, useToday } from "./useToday"
import { useNow } from "./useNow"

function SectionTitle({ children }: { children: string }) {
  return (
    <h2 className="font-sans text-xs font-medium text-muted-foreground">
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

  return (
    <ScrollArea className="min-h-0 flex-1">
      <main className="mx-auto flex max-w-3xl flex-col gap-7 p-6">
        <PageHeader
          title="Today"
          description={
            data
              ? `${data.card.unread} unread · ${data.card.approvals.length} waiting for approval`
              : isError
                ? "Could not load today. Trying again shortly."
                : "Loading"
          }
        />

        <GoogleBanner status={data?.google} />

        {line && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="health-line"
          >
            {line}
          </p>
        )}

        {data?.background_refresh === false && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="refresh-note"
          >
            Background refresh is off
          </p>
        )}

        {isPending && <TodaySkeleton />}

        {data && <DayCard card={data.card} now={now} />}

        {data && (
          <BriefPanel
            brief={data.brief}
            digest={data.digest}
            showing={data.showing}
          />
        )}

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
                    {clockTime(reminder.due_at)}
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
