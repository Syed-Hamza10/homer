import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { FormField } from "./FormField"
import type { MailEdit } from "./types"

type Props = { value: MailEdit; onChange: (value: MailEdit) => void }

export function MailForm({ value, onChange }: Props) {
  return (
    <>
      <FormField label="To">
        <Input
          value={value.to}
          onChange={(e) => onChange({ ...value, to: e.target.value })}
        />
      </FormField>
      <FormField label="Subject">
        <Input
          value={value.subject}
          onChange={(e) => onChange({ ...value, subject: e.target.value })}
        />
      </FormField>
      <FormField label="Body">
        <Textarea
          value={value.body}
          onChange={(e) => onChange({ ...value, body: e.target.value })}
        />
      </FormField>
    </>
  )
}
