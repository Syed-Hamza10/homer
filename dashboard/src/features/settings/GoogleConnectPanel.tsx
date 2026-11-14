import { useState } from "react"
import { Button } from "@/components/ui/button"
import { connectStep } from "./googleStatus"
import type { GoogleStatus } from "./types"

const GOOGLE_SETUP_URL =
  "https://github.com/Syed-Hamza10/homer/blob/main/docs/GOOGLE_SETUP.md"

const panelClass =
  "flex flex-col gap-3 rounded-md border border-border/70 p-3 text-sm"

type Props = {
  status: GoogleStatus
  pending: boolean
  onConnect: () => void
  onCheck: () => void
}

function MissingClient({
  path,
  onCheck,
}: {
  path: string
  onCheck: () => void
}) {
  return (
    <div data-testid="google-setup" className={panelClass}>
      <p>
        Homer needs a Google OAuth client before it can sign in to Google. It is
        a small file from your own Google Cloud project. Making it takes about
        15 minutes, once.
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
          to create a Desktop OAuth client and download its file.
        </li>
        <li>
          Save the file exactly here:{" "}
          <code className="break-all text-foreground">{path}</code>
        </li>
        <li>Press Check again.</li>
      </ol>
      <div>
        <Button variant="outline" onClick={onCheck}>
          Check again
        </Button>
      </div>
    </div>
  )
}

function SignInLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div data-testid="google-waiting" className={panelClass}>
      <p>
        Open this link in a private/incognito window and sign in with the Google
        account you want Homer to use.
      </p>
      <p className="text-muted-foreground">
        Google shows an error when you're signed into several accounts at once.
        A private window avoids it.
      </p>
      <code className="break-all rounded-sm bg-muted px-2 py-1.5 text-xs">
        {url}
      </code>
      <div className="flex items-center gap-2">
        <Button variant="outline" onClick={copy}>
          {copied ? "Copied" : "Copy link"}
        </Button>
        <Button asChild variant="ghost">
          <a href={url} target="_blank" rel="noreferrer">
            Open
          </a>
        </Button>
      </div>
      <p className="text-muted-foreground" aria-live="polite">
        Waiting for Google. This page updates when you finish signing in.
      </p>
    </div>
  )
}

export function GoogleConnectPanel({
  status,
  pending,
  onConnect,
  onCheck,
}: Props) {
  const step = connectStep(status)

  if (step === "missing")
    return <MissingClient path={status.client_secret_path} onCheck={onCheck} />
  if (step === "waiting" && status.auth_url)
    return <SignInLink url={status.auth_url} />
  if (step === "connected")
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <p data-testid="google-connected">
          Connected as{" "}
          <span className="font-medium">
            {status.email ?? "your Google account"}
          </span>
        </p>
        <Button variant="outline" disabled={pending} onClick={onConnect}>
          Reconnect
        </Button>
      </div>
    )
  const expired = status.state === "expired"
  return (
    <div data-testid="google-ready" className={panelClass}>
      <p>
        {expired
          ? "Google's permission for Homer has run out. Sign in again to keep mail and calendar working."
          : "Connect the Google account Homer should use for mail, calendar and contacts. Homer gives you a sign-in link to open in a private window."}
      </p>
      <div>
        <Button disabled={pending} onClick={onConnect}>
          {expired ? "Reconnect" : "Sign in with Google"}
        </Button>
      </div>
    </div>
  )
}
