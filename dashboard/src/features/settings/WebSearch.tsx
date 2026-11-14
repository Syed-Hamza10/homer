import { useState, type FormEvent } from "react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  keyedProvider,
  keyLinks,
  privacyLine,
  probeText,
  providerNames,
} from "./searchText"
import type { KeyedProvider, SearchProvider, SearchSettings } from "./types"
import { useSaveSearch, useSearchSettings, useTestSearch } from "./useSearch"

const selectClass =
  "h-8 w-full rounded-md border border-input bg-card/60 px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 dark:bg-input/20"

function SearchForm({ initial }: { initial: SearchSettings }) {
  const [provider, setProvider] = useState<SearchProvider>(initial.provider)
  const [apiProvider, setApiProvider] = useState<KeyedProvider>(
    initial.api_provider,
  )
  const [fallback, setFallback] = useState(initial.fallback)
  const [apiKey, setApiKey] = useState("")
  const save = useSaveSearch()
  const probe = useTestSearch()
  const keyed = keyedProvider(provider, apiProvider)
  const hasKey = Boolean(apiKey.trim() || initial.key_hint)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate(
      {
        provider,
        api_provider: apiProvider,
        fallback,
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      },
      { onSuccess: () => setApiKey("") },
    )
  }

  const removeKey = () =>
    save.mutate({ provider, api_provider: apiProvider, fallback, api_key: "" })

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-xs font-medium text-muted-foreground">
            Search with
          </span>
          <select
            className={selectClass}
            value={provider}
            onChange={(event) =>
              setProvider(event.target.value as SearchProvider)
            }
          >
            <option value="duckduckgo">DuckDuckGo (no key needed)</option>
            <option value="brave">Brave Search (needs a key)</option>
            <option value="tavily">Tavily (needs a key)</option>
          </select>
        </label>
        {provider === "duckduckgo" && (
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-xs font-medium text-muted-foreground">
              Backup service for the key
            </span>
            <select
              className={selectClass}
              value={apiProvider}
              onChange={(event) =>
                setApiProvider(event.target.value as KeyedProvider)
              }
            >
              <option value="brave">Brave Search</option>
              <option value="tavily">Tavily</option>
            </select>
          </label>
        )}
      </div>
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="text-xs font-medium text-muted-foreground">
          {providerNames[keyed]} API key
        </span>
        <Input
          type="password"
          autoComplete="off"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder={
            initial.key_hint ? `Saved · ${initial.key_hint}` : "Not set"
          }
          data-testid="search-key"
        />
      </label>
      <p className="text-xs text-muted-foreground">
        Get a free key from{" "}
        <a
          className="underline"
          href={keyLinks.brave}
          target="_blank"
          rel="noreferrer"
        >
          Brave Search
        </a>{" "}
        or{" "}
        <a
          className="underline"
          href={keyLinks.tavily}
          target="_blank"
          rel="noreferrer"
        >
          Tavily
        </a>
        .
      </p>
      {provider === "duckduckgo" && (
        <label className="flex items-center gap-2.5 text-sm">
          <input
            type="checkbox"
            checked={fallback}
            onChange={(event) => setFallback(event.target.checked)}
          />
          Use the key when DuckDuckGo blocks a search
        </label>
      )}
      <p className="text-sm text-muted-foreground" data-testid="search-privacy">
        {privacyLine(provider, apiProvider, hasKey, fallback)}
      </p>
      <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
        <Button type="submit" disabled={save.isPending}>
          Save
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={probe.isPending}
          onClick={() => probe.mutate()}
        >
          Test search
        </Button>
        {initial.key_hint && (
          <Button
            type="button"
            variant="ghost"
            disabled={save.isPending}
            onClick={removeKey}
          >
            Remove key
          </Button>
        )}
        {save.isSuccess && (
          <span className="text-sm text-muted-foreground">Saved.</span>
        )}
        {save.error && (
          <span className="text-sm text-destructive">{save.error.message}</span>
        )}
      </div>
      {probe.data && (
        <p
          className={
            probe.data.status === "ok"
              ? "text-sm text-muted-foreground"
              : "text-sm text-destructive"
          }
          data-testid="search-probe"
        >
          {probeText(probe.data)}
        </p>
      )}
      {probe.error && (
        <p className="text-sm text-destructive">{probe.error.message}</p>
      )}
    </form>
  )
}

export function WebSearch() {
  const { data } = useSearchSettings()

  return (
    <Card data-testid="web-search">
      <CardHeader>
        <CardTitle>Web search</CardTitle>
        <CardDescription>
          DuckDuckGo works without a key. A key is stored only on this computer
          and is never shown again in full.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {data ? (
          <SearchForm initial={data} />
        ) : (
          <p className="text-sm text-muted-foreground">Loading.</p>
        )}
      </CardContent>
    </Card>
  )
}
