# Recording the two-minute demo

One take, about two minutes, screen only. The persona is Dana Whitfield, an independent brand
consultant; every address ends in `example.test`. Nothing in the recording is real client data.

## Pre-flight (10 minutes before)

```sh
ollama serve                                             # or make sure it is already running
ollama run qwen3.5:9b "Say OK"                           # warms the model outside the app (not logged)
cd ~/code/achilles
make build                                               # dashboard into achilles_core/static
uv run achilles-mcp-google-setup                         # only if the token is older than 7 days
uv run python scripts/seed_demo.py --target google       # idempotent; --wipe removes the demo items
uv run achilles doctor                                   # all green before the next line
mv ~/.achilles/data ~/.achilles/data.$(date +%s)         # fresh database: empty outbound log and $0.00
uv run achilles serve                                    # http://127.0.0.1:8000, keep this terminal open
```

Checklist before pressing record:

- [ ] `ollama ps` shows `qwen3.5:9b` loaded and `doctor` was green before the database move.
- [ ] Gmail in a second tab, signed in to the throwaway account, Inbox showing the seeded threads.
- [ ] Browser window 1440x900, zoom 125%, bookmarks bar hidden, one tab for Achilles and one for Gmail.
- [ ] Terminal 120x30, font 16pt, in a third window ready for `uv run achilles doctor`.
- [ ] Log in to Achilles (passphrase) before recording so the first frame is the Privacy page.
- [ ] Do not open `/api/health` or run `doctor` after the fresh database: both log an Ollama call.

## Storyboard (type the prompts exactly)

| Time | Screen | Say |
|---|---|---|
| 0:00 | Privacy page: "No outbound calls yet", Spent on inference: $0.00 | "Fresh install. The model is on this Mac, and the app has not talked to anything yet." |
| 0:10 | Chat. Type: `What is on my calendar tomorrow?` | "Two events tomorrow. The grey lines are the tool calls: one call to the calendar, nothing else." |
| 0:30 | Type: `Find the latest email from the client about the proposal and draft a reply saying I will send the revised version by Friday, then send it` | "It searches, reads the thread, writes the draft, and stops." |
| 0:55 | Approval card: `mail_send`, the preview with To, Subject and body | "Nothing left the machine. Sending is an approval I decide on; the model has no send button." |
| 1:05 | Click **Approve**. Card shows `done`. Switch to the Gmail tab, open Sent | "Approved. There it is in Sent, in Rosa's thread." |
| 1:20 | Back to chat. Type: `Draft a reply to the latest email from the accounts team saying the reissued invoice with the PO number goes out tomorrow, then send it` | "Same flow, but this time I say no." |
| 1:40 | Click **Reject**. Card shows `rejected`. Gmail Sent unchanged | "Rejected means nothing happened." |
| 1:48 | Privacy page: `127.0.0.1:11434` and `www.googleapis.com` (plus `oauth2.googleapis.com` if the token refreshed), with call counts | "Every outbound call, by host. Ollama and Google. No AI provider, no per-token bill." |
| 1:55 | Terminal: `uv run achilles doctor` | "And this is the install check a client runs." |

If the model only drafts and does not ask to send, type `Send that draft now with mail_send.` and
carry on; the real-stack tests allow the same follow-up. If the model sends before you expect it,
nothing is lost: it cannot, the card is the only way.

## After recording

`uv run python scripts/seed_demo.py --target google --wipe` trashes the demo mail and deletes the
demo events. The sent reply stays in Sent; delete it by hand if you want the account clean.
