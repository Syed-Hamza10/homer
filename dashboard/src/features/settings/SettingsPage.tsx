import { useState, type FormEvent, type ReactNode } from "react"
import { PageHeader } from "@/components/PageHeader"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Textarea } from "@/components/ui/textarea"
import { GoogleAccount } from "./GoogleAccount"
import { ModelHint } from "./ModelHint"
import { TimezoneSelect } from "./TimezoneSelect"
import type { ClientRules, ModelTier, SelfEmailStatus } from "./types"
import {
  useHealth,
  useModelOptions,
  useRules,
  useSaveRules,
  useSmoke,
} from "./useSettings"

const tierLabels: Record<ModelTier, string> = {
  supported: "Quality (9B model)",
  degraded: "Fast (4B model)",
}

const selfEmailNotes: Partial<Record<SelfEmailStatus, string>> = {
  mismatch:
    "Paused: this address is not the connected Google account, so briefs are not emailed.",
  unknown:
    "Cannot check this address against the connected Google account right now.",
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

function RulesForm({ initial }: { initial: ClientRules }) {
  const [signature, setSignature] = useState(initial.signature)
  const [tone, setTone] = useState(initial.tone)
  const [hours, setHours] = useState(initial.business_hours)
  const [days, setDays] = useState(initial.follow_up_days)
  const [contacts, setContacts] = useState(initial.priority_contacts.join("\n"))
  const [selfEmail, setSelfEmail] = useState(initial.self_email)
  const [emailToSelf, setEmailToSelf] = useState(initial.email_to_self)
  const [modelTier, setModelTier] = useState(initial.model_tier ?? "")
  const [timezone, setTimezone] = useState(initial.timezone)
  const save = useSaveRules()
  const options = useModelOptions()
  const smoke = useSmoke()
  const health = useHealth()
  const selfEmailNote = health.data && selfEmailNotes[health.data.self_email]

  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate({
      signature,
      tone,
      business_hours: hours,
      follow_up_days: days,
      priority_contacts: contacts
        .split(/[\n,]/)
        .map((value) => value.trim())
        .filter(Boolean),
      email_to_self: emailToSelf,
      self_email: selfEmail,
      model_tier: modelTier ? (modelTier as ModelTier) : null,
      timezone,
    })
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <Field label="Signature">
        <Textarea
          value={signature}
          onChange={(event) => setSignature(event.target.value)}
          placeholder="Jordan"
        />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Tone for drafted replies">
          <Input
            value={tone}
            onChange={(event) => setTone(event.target.value)}
          />
        </Field>
        <Field label="Business hours">
          <Input
            value={hours}
            onChange={(event) => setHours(event.target.value)}
            placeholder="09:00-17:00"
            aria-invalid={
              /^\d{2}:\d{2}-\d{2}:\d{2}$/.test(hours) ? undefined : true
            }
          />
        </Field>
        <Field label="Timezone">
          <TimezoneSelect value={timezone} onChange={setTimezone} />
        </Field>
        <Field label="Default follow-up delay (days)">
          <Input
            type="number"
            min={1}
            max={30}
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            className="w-24"
          />
        </Field>
        <Field label="Your email address (for sending yourself the brief)">
          <Input
            value={selfEmail}
            onChange={(event) => setSelfEmail(event.target.value)}
            placeholder="you@example.test"
          />
        </Field>
      </div>
      <Field label="Priority contacts, one per line">
        <Textarea
          value={contacts}
          onChange={(event) => setContacts(event.target.value)}
          placeholder="maya@example.test"
        />
      </Field>
      <label className="flex items-center gap-2.5 text-sm">
        <input
          type="checkbox"
          checked={emailToSelf}
          onChange={(event) => setEmailToSelf(event.target.checked)}
        />
        Email the morning brief and digest to me
      </label>
      {selfEmailNote && (
        <p className="text-sm text-destructive" data-testid="self-email-note">
          {selfEmailNote}
        </p>
      )}
      <Field label="AI model">
        <select
          className="h-8 w-full rounded-md border border-input bg-card/60 px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 dark:bg-input/20"
          value={modelTier}
          onChange={(event) => setModelTier(event.target.value)}
        >
          <option value="">Automatic</option>
          {options.data?.tiers.map((tier) => (
            <option key={tier.tier} value={tier.tier}>
              {tierLabels[tier.tier]}
            </option>
          ))}
        </select>
      </Field>
      {options.data && (
        <p className="text-xs text-muted-foreground">
          Currently using: {tierLabels[options.data.effective_tier]}
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        A changed model or timezone takes effect after Homer restarts.
      </p>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={smoke.isPending}
          onClick={() => smoke.mutate(modelTier || null)}
        >
          Check the model
        </Button>
        {smoke.data && (
          <span
            className={
              smoke.data.ok
                ? "text-sm text-muted-foreground"
                : "text-sm text-destructive"
            }
          >
            {smoke.data.ok
              ? `${smoke.data.text} in ${smoke.data.latency_ms} ms`
              : `Failed: ${smoke.data.error}`}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 border-t border-border pt-4">
        <Button type="submit" disabled={save.isPending}>
          Save
        </Button>
        {save.isSuccess && (
          <span className="text-sm text-muted-foreground">Saved.</span>
        )}
        {save.error && (
          <span className="text-sm text-destructive">{save.error.message}</span>
        )}
      </div>
    </form>
  )
}

export function SettingsPage() {
  const { data } = useRules()

  return (
    <ScrollArea className="min-h-0 flex-1">
      <main className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
        <PageHeader
          title="Settings"
          description="These preferences shape how Homer sorts mail, drafts replies and tracks follow-ups."
        />
        <ModelHint />
        <Card>
          <CardHeader>
            <CardTitle>Your preferences</CardTitle>
            <CardDescription>Stored only on this computer.</CardDescription>
          </CardHeader>
          <CardContent>
            {data ? (
              <RulesForm initial={data} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Loading your preferences.
              </p>
            )}
          </CardContent>
        </Card>
        <GoogleAccount />
      </main>
    </ScrollArea>
  )
}
