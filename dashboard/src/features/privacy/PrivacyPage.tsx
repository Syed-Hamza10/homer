import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { StatusLine } from "@/features/chat/StatusLine"
import { useHosts, useSetWebSearch, useUsage, useWipe } from "./usePrivacy"

export function PrivacyPage() {
  const { data: hosts } = useHosts()
  const { data: usage } = useUsage()
  const setWebSearch = useSetWebSearch()
  const wipe = useWipe()
  const tokens = usage ? usage.input_tokens + usage.output_tokens : 0

  const confirmWipe = () => {
    if (
      window.confirm(
        "Delete local conversations, mail cache, approvals and logs?",
      )
    )
      wipe.mutate()
  }

  return (
    <ScrollArea className="min-h-0 flex-1">
      <main className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
        <section className="flex flex-col gap-2">
          <h1 className="text-lg font-semibold">Privacy</h1>
          <p className="text-sm text-muted-foreground">
            Every outbound call the app made, by host. The model runs on this
            machine.
          </p>
          <StatusLine tokens={tokens} />
          <div className="flex items-center gap-3 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={hosts?.web_search_configured ?? false}
                disabled={!hosts || setWebSearch.isPending}
                onChange={(event) => setWebSearch.mutate(event.target.checked)}
              />
              Web search
            </label>
            <span className="text-xs text-muted-foreground">
              Running: {hosts?.web_search ? "on" : "off"}
            </span>
          </div>
          {setWebSearch.data?.restart_required && (
            <p className="text-xs text-muted-foreground">
              Restart Achilles to apply the web search change.
            </p>
          )}
          {setWebSearch.error && (
            <p className="text-xs text-destructive">
              {setWebSearch.error.message}
            </p>
          )}
        </section>

        <section className="flex gap-6 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Input tokens</p>
            <p>{usage?.input_tokens.toLocaleString() ?? 0}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Output tokens</p>
            <p>{usage?.output_tokens.toLocaleString() ?? 0}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Requests</p>
            <p>{usage?.requests.toLocaleString() ?? 0}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Spent on inference</p>
            <p>${(usage?.spent_usd ?? 0).toFixed(2)}</p>
          </div>
        </section>

        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-2 font-medium">Host</th>
              <th className="py-2 font-medium">Calls</th>
              <th className="py-2 font-medium">Last seen</th>
            </tr>
          </thead>
          <tbody>
            {hosts?.hosts.map((row) => (
              <tr key={row.host} className="border-t">
                <td className="py-2 font-mono">{row.host}</td>
                <td className="py-2">{row.calls.toLocaleString()}</td>
                <td className="py-2">
                  {new Date(row.last_seen).toLocaleString()}
                </td>
              </tr>
            ))}
            {hosts && hosts.hosts.length === 0 && (
              <tr className="border-t">
                <td colSpan={3} className="py-2 text-muted-foreground">
                  No outbound calls yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <section className="flex flex-col gap-2 border-t pt-4">
          <h2 className="text-sm font-semibold">Local data</h2>
          <p className="text-sm text-muted-foreground">
            Removes conversations, cached mail and calendar, briefs, follow-ups,
            approvals, reminders and the outbound log. Settings and credentials
            stay.
          </p>
          <Button
            variant="destructive"
            size="sm"
            className="self-start"
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
