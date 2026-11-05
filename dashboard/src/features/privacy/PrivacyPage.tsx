import { PageHeader } from "@/components/PageHeader"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { StatusLine } from "@/features/chat/StatusLine"
import { useHosts, useSetWebSearch, useUsage, useWipe } from "./usePrivacy"

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-card/70 px-4 py-3 shadow-[inset_0_1px_0_var(--marble-1)]">
      <p className="text-[9px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 font-heading text-xl tabular-nums">{value}</p>
    </div>
  )
}

export function PrivacyPage() {
  const { data: hosts } = useHosts()
  const { data: usage } = useUsage()
  const setWebSearch = useSetWebSearch()
  const wipe = useWipe()
  const tokens = usage ? usage.input_tokens + usage.output_tokens : 0

  const confirmWipe = () => {
    if (
      window.confirm(
        "Delete saved conversations, mail copies, approvals and history?",
      )
    )
      wipe.mutate()
  }

  return (
    <ScrollArea className="min-h-0 flex-1">
      <main className="mx-auto flex max-w-3xl flex-col gap-7 p-6">
        <PageHeader
          eyebrow="Trust"
          title="Privacy"
          description="Every website or service Homer has contacted, and how often. The AI itself runs on this machine."
        />
        <StatusLine tokens={tokens} />

        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat
            label="Text read by the AI"
            value={usage?.input_tokens.toLocaleString() ?? "0"}
          />
          <Stat
            label="Text written by the AI"
            value={usage?.output_tokens.toLocaleString() ?? "0"}
          />
          <Stat
            label="Requests"
            value={usage?.requests.toLocaleString() ?? "0"}
          />
          <Stat
            label="Spent on AI"
            value={`$${(usage?.spent_usd ?? 0).toFixed(2)}`}
          />
        </section>

        <Card size="sm">
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2.5 text-sm">
              <input
                type="checkbox"
                checked={hosts?.web_search_configured ?? false}
                disabled={!hosts || setWebSearch.isPending}
                onChange={(event) => setWebSearch.mutate(event.target.checked)}
              />
              Web search
            </label>
            <span className="text-[10px] tracking-[0.18em] uppercase text-muted-foreground">
              Right now: {hosts?.web_search ? "on" : "off"}
            </span>
            {setWebSearch.data?.restart_required && (
              <p className="w-full text-xs text-muted-foreground">
                Restart Homer to apply this change.
              </p>
            )}
            {setWebSearch.error && (
              <p className="w-full text-xs text-destructive">
                {setWebSearch.error.message}
              </p>
            )}
          </CardContent>
        </Card>

        <div className="overflow-x-auto rounded-lg border border-border bg-card/60 shadow-[inset_0_1px_0_var(--marble-1)]">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-[9px] tracking-[0.22em] uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2.5 font-medium">Service</th>
                <th className="px-3 py-2.5 font-medium">Times contacted</th>
                <th className="px-3 py-2.5 font-medium">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {hosts?.hosts.map((row) => (
                <tr
                  key={row.host}
                  className="border-t border-border/70 transition-colors hover:bg-muted/30"
                >
                  <td className="px-3 py-2.5 font-mono text-xs">{row.host}</td>
                  <td className="px-3 py-2.5 tabular-nums">
                    {row.calls.toLocaleString()}
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground">
                    {new Date(row.last_seen).toLocaleString()}
                  </td>
                </tr>
              ))}
              {hosts && hosts.hosts.length === 0 && (
                <tr className="border-t border-border/70">
                  <td colSpan={3} className="px-3 py-6 text-muted-foreground">
                    Homer has not contacted anything yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <section className="flex flex-col gap-2.5 border-t border-border pt-5">
          <h2 className="text-[9px] font-medium tracking-[0.3em] uppercase text-muted-foreground">
            Local data
          </h2>
          <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">
            Removes conversations, saved copies of mail and calendar, briefs,
            follow-ups, approvals, reminders and this contact history. Your
            preferences and Google sign-in stay.
          </p>
          <Button
            variant="destructive"
            size="sm"
            className="mt-1 self-start"
            disabled={wipe.isPending}
            onClick={confirmWipe}
          >
            Wipe local data
          </Button>
          {wipe.data && (
            <p className="text-xs text-muted-foreground">
              Deleted{" "}
              {Object.entries(wipe.data.deleted)
                .filter(([, count]) => count > 0)
                .map(([name, count]) => `${count} ${name}`)
                .join(", ") || "nothing"}
              .
            </p>
          )}
          {wipe.error && (
            <p className="text-xs text-destructive">{wipe.error.message}</p>
          )}
        </section>
      </main>
    </ScrollArea>
  )
}
