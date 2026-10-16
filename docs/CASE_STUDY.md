# Achilles: a private AI assistant for Gmail and Calendar

## The problem
Small agencies and consultants run their business through Gmail: inquiries, proposals, invoices,
meeting requests. The hosted AI assistants that could help read all of that mail on someone else's
servers, bill per token, and give an admin no way to see what left the building. Many of these
teams, and the clients they sign NDAs with, cannot accept that.

## What Achilles does
Achilles runs on the user's own computer. A local language model (Qwen 3.5 9B through Ollama)
answers questions about mail and calendar, drafts replies in context, and proposes actions. The
user talks to it in a browser on `localhost`. Today it reads and searches mail, reads the calendar,
finds free slots, drafts replies, and sends mail or creates and changes events only after the user
presses Approve. Triage with labels, a morning brief, follow-up tracking and document-grounded
answers are the next steps.

## How privacy is enforced
- **One HTTP client.** Every outbound call in the codebase goes through one allowlisted client. A
  lint rule blocks every other HTTP library. The allowlist holds the local Ollama address and the
  Google API hosts; anything else is refused before a connection is opened, and a test proves it.
- **Outbound log.** Each call is written to a local SQLite table (host, path, status, duration).
  The Privacy page shows that table grouped by host. After a demo it reads exactly `127.0.0.1:11434`
  (Ollama), `www.googleapis.com` and `oauth2.googleapis.com` (token refresh), with call counts, and
  "Spent on inference: $0.00".
- **Approvals enforced by the backend.** Tools that send or change anything return a proposal
  (action, payload, preview) instead of acting. The server stores it with a hash and shows a card.
  The code that performs the action is hidden from the model entirely; only the approval handler
  can call it, after the user's click, and a double click is refused by the database.
- **Untrusted content.** Email bodies and web pages are marked as data. Once the model has read any,
  even low-risk actions such as labelling need approval for the rest of that conversation.

## Measured numbers
Dev machine: Apple M3 Pro, 18 GB, macOS. Model `qwen3.5:9b` (4-bit), thinking off. Measured on
2026-10-16 against the real server, the real tool servers and the Google simulator.

| What | Number |
|---|---|
| Generation speed (Ollama, 241-token answer) | 28 tokens/s |
| Memory while the model is loaded | 7.7 GB resident at 16k context (spike); `ollama ps` reports 11 GB with the MLX runner |
| Cold start: model load into memory | about 10 s, once per session |
| "What is on my calendar tomorrow?" | 10.4 s the first time in a session (the model reads the tool schemas once), 3.8 s afterwards; 15.1 s in the end-to-end suite including a cold load |
| Find the proposal email, draft the reply, ask to send (4 tool calls) | 16.2 s to the approval card |
| Approve: hash check plus the real send | 0.02 s |
| Find the invoice thread, draft, ask to send | 18.9 s to the approval card; 14.3 s for the equivalent step in the end-to-end suite |
| Tokens per draft-and-send flow | about 9,500 in, 280 out |

Task success in the rehearsal: 2 of 2 calendar questions correct (both events, right times), 2 of 2
draft-and-send flows ended in a correct approval card addressed to the right person in the right
thread, 1 approved and delivered, 1 rejected and not sent. The first rehearsal failed once: the model
searched for "proposal client", found nothing and gave up. One line in the system prompt about how
mail search matches words fixed it; the retry is now visible in the tool lines.

## Test strategy
150 fast tests run in 35 s with no model and no network: a fake model, a simulator of the Gmail,
Calendar and People APIs, and stand-in tool servers. 20 end-to-end tests start the real server, the
real tool servers, the simulator, the live 9B model and a real browser: a calendar question, a
draft-and-send with approval, a rejection that sends nothing, the approvals page, the privacy page.
They skip themselves when Ollama is not available, so CI stays green on a machine without a GPU.
The demo seed is tested too: it is idempotent and its wipe removes only what it created.

## What it costs to run
Nothing per token and no subscription for inference. The client needs a machine with 16 GB of
memory (18 GB or more is comfortable), 30 GB of free disk and a recent Apple Silicon Mac or a Linux
box with an 8 GB GPU; a 4B model runs on less at lower quality. Google Workspace needs a one-time
OAuth setup by the admin, with no Google verification for an internal app.

## Limitations
- **Small model.** A 9B model is good at reading, drafting and simple tool use; it is not a frontier
  model. Long reasoning, many-step planning and ambiguous requests fail more often, which is why
  every action ends in a human decision.
- **Testing-mode OAuth for non-Workspace users.** A plain Gmail account runs the app in Google's
  Testing mode and must re-consent every 7 days. Workspace teams with an internal app do not.
- **English only** in the interface and the prompts.
- **macOS and Linux today.** Windows install and packaging are planned, not done.
- **Speed is the machine's speed.** The first question after start takes about 10 seconds longer;
  a full draft-and-send takes 15 to 20 seconds on an M3 Pro and more on slower hardware.
