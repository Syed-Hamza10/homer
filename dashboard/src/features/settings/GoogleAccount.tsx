import { ErrorNotice } from "@/components/ErrorNotice"
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

const GOOGLE_SETUP_URL =
  "https://github.com/Syed-Hamza10/homer/blob/main/docs/GOOGLE_SETUP.md"

type RowProps = { label: string; value: string; alert?: boolean }

function Row({ label, value, alert = false }: RowProps) {
  return (
    <div className="flex justify-between gap-4 border-t border-border/70 py-2.5 text-sm">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className={cn(alert && "text-destructive")}>{value}</span>
    </div>
  )
}

function SetupSteps({ path }: { path: string }) {
  return (
    <div
      data-testid="google-setup"
      className="flex flex-col gap-2 rounded-md border border-border/70 p-3 text-sm"
    >
      <p>
        Before you connect, Homer needs a sign-in file from your own Google
        Cloud project. It takes about 15 minutes, once.
      </p>
      <ol className="list-decimal pl-5 text-muted-foreground">
        <li>
          Follow{" "}
          <a
            className="underline"
            href={GOOGLE_SETUP_URL}
            target="_blank"
            rel="noreferrer"
          >
            the Google setup guide
          </a>{" "}
          to create a Desktop OAuth client.
        </li>
        <li>
          Save the downloaded file as <code className="break-all">{path}</code>
        </li>
        <li>Press Connect and sign in with Google.</li>
      </ol>
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
        {data?.state === "not_connected" && !data.client_secret_found && (
          <SetupSteps path={data.client_secret_path} />
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
          <ErrorNotice error={connect.error} onRetry={() => connect.mutate()} />
        </div>
      </CardContent>
    </Card>
  )
}
