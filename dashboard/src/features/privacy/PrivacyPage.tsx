import { ScrollArea } from "@/components/ui/scroll-area"
import { StatusLine } from "@/features/chat/StatusLine"
import { useHosts, useUsage } from "./usePrivacy"

export function PrivacyPage() {
  const { data: hosts } = useHosts()
  const { data: usage } = useUsage()
  const tokens = usage ? usage.input_tokens + usage.output_tokens : 0

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
          <p className="text-xs text-muted-foreground">
            Web search: {hosts?.web_search ? "on" : "off"}
          </p>
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
      </main>
    </ScrollArea>
  )
}
