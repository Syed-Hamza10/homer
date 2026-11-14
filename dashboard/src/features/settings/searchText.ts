import type { KeyedProvider, SearchProbe, SearchProvider } from "./types"

export const providerNames: Record<SearchProvider, string> = {
  duckduckgo: "DuckDuckGo",
  brave: "Brave Search",
  tavily: "Tavily",
}

export const keyLinks: Record<KeyedProvider, string> = {
  brave: "https://brave.com/search/api/",
  tavily: "https://tavily.com/",
}

export function keyedProvider(
  provider: SearchProvider,
  apiProvider: KeyedProvider,
): KeyedProvider {
  return provider === "duckduckgo" ? apiProvider : provider
}

export function privacyLine(
  provider: SearchProvider,
  apiProvider: KeyedProvider,
  hasKey: boolean,
  fallback: boolean,
): string {
  const keyed = providerNames[keyedProvider(provider, apiProvider)]
  const services = !hasKey
    ? providerNames.duckduckgo
    : provider !== "duckduckgo"
      ? keyed
      : fallback
        ? `${providerNames.duckduckgo} (or ${keyed} when it blocks)`
        : providerNames.duckduckgo
  return `Your search question goes to ${services}. Emails and documents never do.`
}

export function probeText(probe: SearchProbe): string {
  const name =
    providerNames[probe.provider as SearchProvider] ?? "the search service"
  switch (probe.status) {
    case "ok":
      return `Works: ${name} answered with ${probe.results} results.`
    case "blocked":
      return `${name} is blocking searches from this computer right now.`
    case "invalid_key":
      return `${name} did not accept the key.`
    case "limited":
      return `${name} says the free searches are used up or too many were sent.`
    case "off":
      return "Web search is turned off on the Privacy page."
    default:
      return `${name} could not be reached.`
  }
}
