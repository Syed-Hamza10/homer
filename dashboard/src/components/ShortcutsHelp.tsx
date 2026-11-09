import { Button } from "@/components/ui/button"
import { useShortcuts } from "@/lib/shortcuts"

export type Shortcut = { keys: string; label: string }

type Props = { title: string; shortcuts: Shortcut[]; onClose: () => void }

export function ShortcutsHelp({ title, shortcuts, onClose }: Props) {
  useShortcuts({ Escape: onClose, "?": onClose })

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`${title} keyboard shortcuts`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex w-full max-w-md flex-col gap-3 rounded-lg border border-border bg-card p-5 shadow-[inset_0_1px_0_var(--marble-1)]"
        onClick={(event) => event.stopPropagation()}
      >
        <p className="text-xs font-medium text-muted-foreground">
          Keyboard shortcuts
        </p>
        <h2 className="font-heading text-xl">{title}</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          {shortcuts.map((shortcut) => (
            <div key={shortcut.keys} className="contents">
              <dt>
                <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs">
                  {shortcut.keys}
                </kbd>
              </dt>
              <dd className="text-muted-foreground">{shortcut.label}</dd>
            </div>
          ))}
        </dl>
        <Button
          size="sm"
          variant="outline"
          className="self-end"
          onClick={onClose}
        >
          Close
        </Button>
      </div>
    </div>
  )
}
