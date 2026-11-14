import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { clockTime } from "./dayFormat"
import type { Brief, BriefKind } from "./types"
import { useRunBrief, useRunDigest } from "./useToday"

type Props = {
  brief: Brief | null
  digest: Brief | null
  showing: BriefKind
}

const names: Record<BriefKind, string> = {
  morning: "Morning brief",
  digest: "End-of-day digest",
}

const other = (kind: BriefKind): BriefKind =>
  kind === "morning" ? "digest" : "morning"

export function BriefPanel({ brief, digest, showing }: Props) {
  const [flipped, setFlipped] = useState(false)
  const runBrief = useRunBrief()
  const runDigest = useRunDigest()
  const kind = flipped ? other(showing) : showing
  const shown = kind === "morning" ? brief : digest
  const run = kind === "morning" ? runBrief : runDigest
  const title = shown
    ? `${names[kind]} · generated ${clockTime(shown.generated_at)}`
    : names[kind]

  return (
    <Card size="sm" data-testid="brief-panel">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardAction>
          <Button
            size="sm"
            variant="outline"
            disabled={run.isPending}
            onClick={() => run.mutate()}
          >
            {run.isPending ? "Refreshing…" : "Refresh"}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm leading-relaxed whitespace-pre-wrap text-muted-foreground">
          {shown?.content ??
            `No ${names[kind].toLowerCase()} yet today. Refresh to make one now.`}
        </p>
        {run.error && (
          <p className="text-sm text-destructive">{run.error.message}</p>
        )}
        <button
          type="button"
          className="self-start text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          onClick={() => setFlipped(!flipped)}
        >
          See the {names[other(kind)].toLowerCase()}
        </button>
      </CardContent>
    </Card>
  )
}
