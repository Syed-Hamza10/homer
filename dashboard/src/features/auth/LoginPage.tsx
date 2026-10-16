import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ApiError, post } from "@/lib/api"

const messages: Record<number, string> = {
  401: "Wrong passphrase",
  429: "Too many attempts, wait a minute",
}

function describe(error: Error | null): string | null {
  if (!error) return null
  if (error instanceof ApiError) return messages[error.status] ?? "Login failed"
  return "Cannot reach the Achilles server"
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
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Achilles</CardTitle>
        </CardHeader>
        <CardContent>
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
            <Button type="submit" disabled={!passphrase || login.isPending}>
              Unlock
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
