import type { ReactNode } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { attendeeLine, personName, untilLabel } from "./dayFormat"
import { DayRow } from "./DayRow"
import type { DayCardData } from "./types"

type Props = { card: DayCardData; now: number }

function clock(value: string): string {
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  })
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1" aria-label={title}>
      <h3 className="pb-1 font-sans text-xs font-medium text-muted-foreground">
        {title}
      </h3>
      <ul className="flex flex-col text-sm">{children}</ul>
    </section>
  )
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`
}

export function DayCard({ card, now }: Props) {
  const { meetings, emails, follow_ups, approvals } = card
  const quiet =
    !meetings.length &&
    !emails.length &&
    !follow_ups.length &&
    !approvals.length
  const summary = [
    plural(meetings.length, "meeting"),
    plural(emails.length, "email") + " need you",
    plural(approvals.length, "approval") + " waiting",
  ].join(" · ")

  return (
    <Card className="animate-enter" data-testid="day-card">
      <CardContent className="flex flex-col gap-5">
        <div className="flex flex-col gap-1">
          <p className="text-xs font-medium text-muted-foreground">Your day</p>
          <h2 className="font-heading text-2xl leading-tight">
            {card.greeting}
          </h2>
          <p className="text-sm text-muted-foreground">{summary}</p>
        </div>

        {meetings.length > 0 && (
          <Group title={plural(meetings.length, "meeting") + " today"}>
            {meetings.map((meeting) => {
              const next = meeting.event_id === card.next_event_id
              return (
                <DayRow
                  key={meeting.event_id}
                  lead={clock(meeting.start)}
                  title={meeting.title || "Untitled"}
                  detail={attendeeLine(meeting.attendees) || undefined}
                  badge={
                    next
                      ? untilLabel(meeting.start, meeting.end, now)
                      : undefined
                  }
                  highlight={next}
                  action={
                    meeting.join_url
                      ? { label: "Join", to: meeting.join_url, external: true }
                      : {
                          label: "Open",
                          to: `/calendar?event=${encodeURIComponent(meeting.event_id)}`,
                        }
                  }
                />
              )
            })}
          </Group>
        )}

        {emails.length > 0 && (
          <Group title="Emails that need you">
            {emails.map((email) => (
              <DayRow
                key={email.message_id}
                title={email.subject || "(no subject)"}
                detail={`${personName(email.sender)} · ${email.reason}`}
                action={{
                  label: "Open",
                  to: `/inbox?thread=${encodeURIComponent(email.thread_id)}`,
                }}
              />
            ))}
          </Group>
        )}

        {follow_ups.length > 0 && (
          <Group title="Follow-ups due">
            {follow_ups.map((followup) => (
              <DayRow
                key={followup.id}
                title={followup.subject || "(no subject)"}
                detail={personName(followup.contact)}
                action={{
                  label: "Open",
                  to: `/inbox?thread=${encodeURIComponent(followup.thread_id)}`,
                }}
              />
            ))}
          </Group>
        )}

        {approvals.length > 0 && (
          <Group title="Waiting for approval">
            {approvals.map((approval) => (
              <DayRow
                key={approval.id}
                title={approval.preview}
                action={{
                  label: "Review",
                  to: `/approvals#approval-${approval.id}`,
                }}
              />
            ))}
          </Group>
        )}

        {quiet && (
          <p className="text-sm text-muted-foreground">
            Nothing needs you right now.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
