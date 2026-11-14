import { Input } from "@/components/ui/input"

type Props = {
  value: string
  signature: string
  onChange: (value: string) => void
}

export function NameField({ value, signature, onChange }: Props) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="text-xs font-medium text-muted-foreground">
        Your name
      </span>
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Jordan Lee"
      />
      {!value.trim() && !signature.trim() && (
        <span className="text-xs text-muted-foreground">
          Add your name so emails are signed.
        </span>
      )}
    </label>
  )
}
