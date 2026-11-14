import { ErrorNotice } from "@/components/ErrorNotice"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import { GoogleConnectPanel } from "./GoogleConnectPanel"
import { statusLabel } from "./googleStatus"
import { useConnectGoogle, useGoogleStatus } from "./useGoogle"

const SIGN_IN_FAILED =
  "Google sign-in could not start. Check that client_secret.json is the file from the setup guide, then try again."

type RowProps = { label: string; value: string; alert?: boolean }

function Row({ label, value, alert = false }: RowProps) {
  return (
    <div className="flex justify-between gap-4 border-t border-border/70 py-2.5 text-sm">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className={cn(alert && "text-destructive")}>{value}</span>
    </div>
  )
}

export function GoogleAccount() {
  const { data, refetch } = useGoogleStatus()
  const connect = useConnectGoogle()
  const healthy = data?.state === "connected"
  const problem =
    connect.error instanceof ApiError && connect.error.status === 409
      ? SIGN_IN_FAILED
      : connect.error

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
        {data && (
          <GoogleConnectPanel
            status={data}
            pending={connect.isPending}
            onConnect={() => connect.mutate()}
            onCheck={() => void refetch()}
          />
        )}
        <ErrorNotice error={problem} onRetry={() => connect.mutate()} />
      </CardContent>
    </Card>
  )
}
