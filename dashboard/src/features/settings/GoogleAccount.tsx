import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { statusLabel } from "./googleStatus"
import { useConnectGoogle, useGoogleStatus } from "./useGoogle"

type RowProps = { label: string; value: string; alert?: boolean }

function Row({ label, value, alert = false }: RowProps) {
  return (
    <div className="flex justify-between gap-4 border-t border-border/70 py-2.5 text-sm">
      <span className="text-[9px] font-medium tracking-[0.22em] uppercase text-muted-foreground">
        {label}
      </span>
      <span className={cn(alert && "text-destructive")}>{value}</span>
    </div>
  )
}

export function GoogleAccount() {
  const { data } = useGoogleStatus()
  const connect = useConnectGoogle()
  const healthy = data?.state === "connected"

  return (
    <Card data-testid="google-account">
      <CardHeader>
        <CardTitle>Google account</CardTitle>
        <CardDescription>Mail, calendar and contacts.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {data ? (
          <div className="flex flex-col">
            <Row label="Address" value={data.email ?? "Unknown"} />
            <Row
              label="Connected on"
              value={
                data.connected_at
                  ? new Date(data.connected_at).toLocaleDateString()
                  : "Never"
              }
            />
            <Row label="Status" value={statusLabel(data)} alert={!healthy} />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Loading.</p>
        )}
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            disabled={connect.isPending}
            onClick={() => connect.mutate()}
          >
            {data?.state === "not_connected" ? "Connect" : "Reconnect"}
          </Button>
          {data?.connecting && (
            <span className="text-sm text-muted-foreground">
              Finish in the browser window that just opened.
            </span>
          )}
          {connect.error && (
            <span className="text-sm text-destructive">
              {connect.error.message}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
