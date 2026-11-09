import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Landmark } from "lucide-react"
import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ApiError, post } from "@/lib/api"

const messages: Record<number, string> = {
  401: "Wrong passphrase",
  429: "Too many attempts, wait a minute",
}

function describe(error: Error | null): string | null {
  if (!error) return null
  if (error instanceof ApiError) return messages[error.status] ?? "Login failed"
  return "Cannot reach Homer. Check that it is running."
}

export function LoginPage() {
  const [passphrase, setPassphrase] = useState("")
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const login = useMutation({
    mutationFn: (value: string) =>
      post("/api/auth/login", { passphrase: value }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["auth"] })
      navigate("/", { replace: true })
    },
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (passphrase) login.mutate(passphrase)
  }

  const error = describe(login.error)

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="flex w-full max-w-sm flex-col items-center gap-7">
        <div className="flex flex-col items-center gap-3 text-center">
          <span className="flex size-14 items-center justify-center rounded-full border border-border bg-card text-foreground shadow-[inset_0_1px_0_var(--marble-1)]">
            <Landmark className="size-6" strokeWidth={1.25} />
          </span>
          <div>
            <p className="font-heading text-[13px] italic text-muted-foreground">
              Your AI assistant, right at home.
            </p>
            <h1 className="mt-1.5 font-heading text-4xl tracking-[0.14em] uppercase">
              Homer
            </h1>
          </div>
          <div aria-hidden className="flex items-center gap-3">
            <span className="h-px w-12 bg-border" />
            <span className="size-1.5 rotate-45 border border-ring/70" />
            <span className="h-px w-12 bg-border" />
          </div>
        </div>
        <Card className="w-full shadow-[0_24px_60px_-40px_oklch(0.25_0.01_65/0.55)]">
          <CardContent className="flex flex-col gap-4 pt-1">
            <p className="text-center text-xs font-medium text-muted-foreground">
              Enter the archive
            </p>
            <form onSubmit={submit} className="flex flex-col gap-3">
              <Input
                type="password"
                autoFocus
                autoComplete="current-password"
                placeholder="Passphrase"
                value={passphrase}
                onChange={(event) => setPassphrase(event.target.value)}
                aria-invalid={error ? true : undefined}
              />
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button
                type="submit"
                disabled={!passphrase || login.isPending}
                className="w-full"
              >
                Unlock
              </Button>
            </form>
          </CardContent>
        </Card>
        <p className="text-center text-xs font-medium text-muted-foreground">
          The AI runs on this machine
        </p>
      </div>
    </main>
  )
}
