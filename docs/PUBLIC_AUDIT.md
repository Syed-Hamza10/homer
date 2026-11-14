# Public release audit

Audit of `Syed-Hamza10/homer` before it goes public, 2026-11-14. It covers the working tree on
`main` (fdfe8da) and every commit reachable from any local or remote ref (223 commits). Tools:
`gitleaks` 8 over `git log --all` and the working tree, regex scans with `git grep` over every
revision, and a path listing of every tree in history.

Severity: **High** blocks going public. **Medium** fix before or on launch day. **Low** clean up
when convenient.

## Findings

### 1. Secrets and credentials

| # | Severity | Where | Finding | Action |
|---|---|---|---|---|
| 1.1 | — | all history, working tree | `gitleaks` found no leaks. No Google OAuth client ids or secrets, `GOCSPX-`, GitHub, Brave, Tavily, OpenAI-style or private keys, `client_secret*.json`, `token*.json` or `.env` in any commit. | None. |
| 1.2 | Low | `.env.example` | `HOMER_PASSPHRASE=change-me` is a placeholder. | Keep. The installer writes the real `.env`. |
| 1.3 | — | GitHub settings | No Actions secrets, releases or tags exist. Only `main` is on the remote. No forks or pull requests. | None. |

### 2. Personal data

| # | Severity | Where | Finding | Action |
|---|---|---|---|---|
| 2.1 | **High** | history: `docs/qa/round1-email.jsonl` and `docs/qa/round1-calsearch.jsonl`, added in merge 102ebdf, deleted in 848a24e, present in 14 commits on `main` | A personal Gmail address of a founder appears 78 times in a QA transcript. `docs/qa/` is gitignored now, but these two files were committed once and are still in `main`'s history. | Purge with the history rewrite below. |
| 2.2 | **High** | history: commits d46e90c and 39d90f3 (author metadata) | Two README commits made in the GitHub web editor carry the same personal Gmail address as author email. | Rewrite the author with a mailmap (below). Get Hassan's agreement on the replacement identity first. |
| 2.3 | Medium | history: `CLAUDE.md` (all 223 versions) and `ACHILLES_IMPLEMENTATION_PLAN_v3.md` / `HOMER_IMPLEMENTATION_PLAN_v3.md` | The founder's company GitHub account name appears. | Fixed in the working tree (8d93d20). For history, add the `--replace-text` rule below to the same rewrite. |
| 2.4 | — | working tree | No personal email, phone number, home path, machine name or employer account remains outside the files moving to `homer-internal`. Test fixtures use `example.test` addresses. | None. |
| 2.5 | Low | many test files and `site/index.html` | Fictional contacts (Rosa Lindgren, Maya Chen and others) and founder first names (Hamza, Hassan) in prompts and fixtures. | Keep; they are fictional or the founders' public names. |
| 2.6 | Low | tests (`a@x.com`, `b@x.com`) | `x.com` is a real domain. | Optional: switch to `example.test`. |

### 3. Internal-only documents

| # | Severity | Where | Finding | Action |
|---|---|---|---|---|
| 3.1 | **High** | `docs/launch/` (ASSESSMENT, YC_APPLICATION, LINKEDIN, DEMO_VIDEO, PRODUCT_GAPS), `docs/HANDOFF.md`, `docs/STATUS.md` | Candid odds assessment, YC drafts, QA scores, pickup notes. In history since 369d980 (2026-10-20) and 6916f09 / 367e657 / d3d7435 (2026-11-06). Deleting them in a new commit leaves every version readable in history. | Founders' decision: move to `homer-internal` and purge from history with the rewrite below. |
| 3.2 | Medium | `docs/PROJECT_GUIDE.md:311` | Links to `STATUS.md`. | Fixed: row removed from `docs/PROJECT_GUIDE.md`. |
| 3.3 | Medium | `docs/EXPLAINERS/*.md` | Every explainer has "How to explain it in an interview" and "What a client may ask" sections. Not secret, but reads as interview prep. | Founders' decision: keep (shows reasoning, fine for a portfolio), rename the headings, or move to `homer-internal`. |
| 3.4 | Low | `HOMER_IMPLEMENTATION_PLAN_v3.md` | Build plan with "what we sell first", target-customer hypothesis and per-step review notes for Hamza. §14 still says `LICENSE` is "Copyright ACHAEA. All rights reserved." | Keep (it is the spec `CLAUDE.md` points to). Update the §14 license line when PolyForm lands. |
| 3.5 | Low | `docs/DECISIONS.md:8` | "Private repo under `Syed-Hamza10`, proprietary license." | Append a new dated line for the public repo and PolyForm license; do not edit history lines. |
| 3.6 | Low | `CLAUDE.md` | Agent instructions, "Keeping Hamza in the loop". Harmless, shows the AI-assisted workflow. | Keep, or move if you prefer not to show it. |

### 4. Licensing

Founders' decision: PolyForm Noncommercial 1.0.0 (applied on another branch).

Dependency inventory (from `uv.lock` and `dashboard/pnpm-lock.yaml`):

| Set | Count | Licenses |
|---|---|---|
| Python runtime | 123 | MIT 57, BSD-3 25, Apache-2.0 18, ISC 4, BSD-2 3, BSD 3, PSF-2.0 2, MIT-0 1, Unlicense 1, dual permissive 6, Apache-2.0 AND CNRI-Python 1 (`regex`), MPL-2.0 1 (`certifi`), MPL-1.1 OR GPL-2.0 OR LGPL-2.1+ 1 (`tld`) |
| Python dev | 16 | MIT 8, Apache-2.0 4, BSD-3 1, MIT AND PSF-2.0 1, MPL-2.0 1 (`pathspec`), Artistic OR GPL-2.0+ 1 (`text-unidecode`) |
| npm prod | 486 resolved, 91 in the bundle | Bundle: all MIT except `class-variance-authority` (Apache-2.0), `lucide-react` and `@ungap/structured-clone` (ISC), `dompurify` (MPL-2.0 OR Apache-2.0); Geist fonts (OFL-1.1) |
| npm dev | 172 | MIT 136, Apache-2.0 17, BSD-2 8, ISC 4, MPL-2.0 4 (`lightningcss`), BSD-3 2, MIT-0 1 |

No dependency is non-commercial, BUSL, SSPL, unlicensed or missing a license.

| # | Severity | Where | Finding | Action |
|---|---|---|---|---|
| 4.1 | — | dependencies | No conflict with PolyForm Noncommercial. Copyleft appears only in packages users install from PyPI themselves (`tld` also offers MPL-1.1, `certifi` is MPL-2.0 and unmodified) or in dev tools. `dompurify` is used under its Apache-2.0 option. | None. |
| 4.2 | Medium | built dashboard in the wheel | The JS bundle keeps no license comments, and there is no `THIRD_PARTY_NOTICES` file. MIT, ISC and Apache-2.0 require the notice to travel with the code. The Geist fonts (OFL-1.1) need their copyright and license text. | Fixed: `THIRD_PARTY_NOTICES.md` at the repo root, with the Geist OFL text; linked from `docs/ARCHITECTURE.md`. Still to do: ship it in the wheel next to `static/`. |
| 4.3 | Low | `dashboard/package.json` | The `shadcn` CLI is in `dependencies`, pulling ~400 packages into the prod tree (none bundled). | Move it to `devDependencies`. |
| 4.4 | Low | `models/manifest.json` | Qwen 3.5 tags and `nomic-embed-text` (Apache-2.0); pulled by Ollama at runtime, not shipped. | Confirm the license on each Ollama tag page and mention it in the README. |

What each common license would mean (facts, not legal advice):

| License | Others may | Portfolio | Upwork clients | YC / company |
|---|---|---|---|---|
| MIT | Use, sell, fork commercially | Best: anyone can read and run it | Clients can take it without you | Investors may ask what the moat is; some open-core startups do this |
| Apache-2.0 | Same as MIT, plus an explicit patent grant | Same | Same | Same as MIT, a bit more corporate-friendly |
| PolyForm Noncommercial 1.0.0 (chosen) | Read, run and modify for non-commercial use only | Good: code is visible | A client running it for their business needs a commercial license from you, which you can sell | Keeps commercial rights with the founders; not OSI open source, so some developers will not contribute |
| BSL 1.1 | Everything except the "Additional Use Grant" limit; converts to an open license after a set date (max 4 years) | Good | Similar to PolyForm NC, but commercial use can be allowed below a threshold you define | Common in funded startups (formerly HashiCorp, Sentry); needs a change date and parameters |
| Elastic 2.0 | Anything except offer it as a hosted service, or bypass license keys | Good | Clients may run it commercially themselves; you cannot charge for self-hosted use under this license alone | Protects against a hosted competitor, which matters less for a local-first app |

Contributions: under PolyForm NC, outside contributions do not automatically give the founders
commercial rights to them. If you plan to sell commercial licenses, either accept no outside
code or add a contributor license agreement. `CONTRIBUTING.md` currently says contributions are
licensed under the repository's terms and asks for an issue first.

### 5. Embarrassments and hygiene

| # | Severity | Where | Finding | Action |
|---|---|---|---|---|
| 5.1 | Medium | `docs/ui-preview/approvals.png`, `calendar.png`, `privacy.png`, `privacy-dark.png`, `settings.png` (2026-11-02) | Sidebar footer shows the old line "Nothing leaves this machine." The app now says "AI runs on this machine." Data shown is fictional. | Fixed: all five retaken (and `login.png`) with the current UI; `docs/ui-preview/index.html` updated. |
| 5.2 | Low | `docs/ui-preview/before/` | Seven "before" screenshots of the previous UI. Dead weight (~3 MB). | Delete unless used in a write-up. |
| 5.3 | Low | `docs/screenshots/main.png` | Shows the previous sidebar and layout; data is fictional, footer is correct. | Retake with the current UI when the README is final. |
| 5.4 | Low | `packages/core/homer_core/models/manifest.json` | Generated, gitignored, but tracked; a second copy of the model tags. | Fixed (9279ef0). The build hook and `llm.py` fallback still find the repo copy; 729 unit tests pass. |
| 5.5 | Medium | `site/index.html:437,443` | Contact is `hello@homer.example`, a placeholder. The waitlist `mailto:` goes nowhere. | Fixed: contact set to `syed.hamza.ds@gmail.com` in `site/` and its README. Confirm it is the address you want public. |
| 5.6 | Low | `site/index.html:252-255` | "Demo video 75 seconds on real Gmail ... Nothing is staged" describes a video that does not exist yet. | Keep the placeholder wording until `demo.mp4` exists. |
| 5.7 | — | working tree | No TODO/FIXME, profanity, debug prints, `__pycache__`, `node_modules`, `dist/` or files over 0.5 MB tracked. Stale "achilles" names only in `docs/HANDOFF.md` and `docs/STATUS.md` (leaving). | None. |
| 5.8 | — | docs | No broken relative links in tracked Markdown or HTML. `ModelHint.tsx` links to `CLIENT_ONBOARDING.md#8-troubleshooting`, which exists. | None. |
| 5.9 | Medium | `PRIVACY.md` | Lists only the default search host. The optional Brave (`api.search.brave.com`) and Tavily (`api.tavily.com`) hosts appear only when configured, so a public reader does not see them. | Fixed: `homer privacy` and `PRIVACY.md` now list both keyed hosts, marked "only if you add a key". |

### 6. Security hygiene

| # | Severity | Where | Finding | Action |
|---|---|---|---|---|
| 6.1 | Medium | `.github/workflows/ci.yml` | No `permissions:` block, so the token used the repo default. Runs on `pull_request` (fork PRs get a read-only token and no secrets; there are no secrets). | Fixed: workflow-level `permissions: contents: read` (9610e05). |
| 6.2 | Low | `.github/workflows/release.yml` | `permissions: contents: write` applies to all three jobs; only `publish` needs it. Triggered by `v*` tags only, so forks cannot run it. | Move `contents: write` to the `publish` job and set `contents: read` at the top. Not edited here because another branch is changing this file. |
| 6.3 | Low | both workflows | Actions pinned by tag (`@v4`, `@v5`), not by commit SHA. | Pin to SHAs, or let Dependabot keep tags current. |
| 6.4 | Medium | `.github/` | No Dependabot or Renovate config. | Fixed: `.github/dependabot.yml` (`uv`, `npm` in `/dashboard`, `github-actions`; weekly, minor and patch grouped). |
| 6.5 | — | repo root | No `SECURITY.md`. | Fixed (2437a11): private reporting through GitHub's "Report a vulnerability". Enable **Settings → Code security → Private vulnerability reporting**. |
| 6.6 | — | repo root | No `CONTRIBUTING.md`. | Fixed (2437a11): minimal guide. A code of conduct only if you want outside contributions. |
| 6.7 | Low | GitHub settings | No branch protection. | Protect `main`: require the `ci` checks, block force pushes and deletion (after the rewrite push). |
| 6.8 | Low | GitHub Actions | 35 workflow runs; their logs become public and point at pre-rewrite SHAs. | Delete old runs after the rewrite (`gh run list --limit 100 --json databaseId -q '.[].databaseId' \| xargs -I{} gh run delete {}`). |
| 6.9 | Low | CI | Dashboard tests (`pnpm test`) and `actionlint` do not run in CI. | Add them to `ci.yml`. |

### 7. Claims

| # | Severity | Where | Finding | Action |
|---|---|---|---|---|
| 7.1 | Medium | `site/index.html:7,206` | "Your emails are never sent to an AI company." Tavily markets itself as a search API for AI agents. With a Tavily key the search question (which the model writes and may include names or details from mail) goes there. | Fixed: "never sent to an AI model provider"; the search line names DuckDuckGo, Brave and Tavily. |
| 7.2 | Low | `site/index.html:309` | "Nothing is sent until you press Send." Email-to-self is sent without approval (tier 2 by policy). | Fine for the landing page; `PRIVACY.md` already states the exception. |
| 7.3 | Low | `PRIVACY.md:11`, `privacy_hosts.py:37` | "No email or document leaves the machine" sits in the Ollama row, where it is true for that host but can read as a global claim. | Fixed: Ollama row now says "Model input stays on this machine." |
| 7.4 | — | `HOMER_IMPLEMENTATION_PLAN_v3.md:14`, `docs/CASE_STUDY.md`, `docs/PROJECT_GUIDE.md:10` | Wording is scoped correctly ("never sent to an AI provider", Google and the search engine named). The 4.4 s median on the site is sourced in `docs/DECISIONS.md:132`. | None. |
| 7.5 | — | `README.md`, `CLIENT_ONBOARDING.md`, `scripts/install.sh` | Being rewritten on other branches; not audited for wording here. `README.md` and `docs/PROJECT_GUIDE.md` clone `https://github.com/Syed-Hamza10/homer.git`, correct once public. `install.sh` and `homer_core/update.py` read `GITHUB_TOKEN`; once public, the token is only needed for rate limits. | Re-check those files for claims 7.1 and 7.3 after they merge. |

## History rewrite

Needed for 2.1, 2.2, 2.3 and 3.1. Run it once, after the internal docs are copied to
`homer-internal` and every branch that matters is merged or pushed. Everyone re-clones afterwards.

```sh
brew install git-filter-repo

git clone --mirror git@github-hamza:Syed-Hamza10/homer.git homer-rewrite.git
cd homer-rewrite.git

cat > ../mailmap.txt <<'MAP'
hassudo <hassudo@users.noreply.github.com> <PERSONAL_GMAIL_ADDRESS>
MAP

cat > ../replacements.txt <<'REP'
PERSONAL_GMAIL_ADDRESS==>hassan@example.test
COMPANY_ACCOUNT_NAME==>a company account
REP

git filter-repo \
  --invert-paths \
  --path docs/launch/ \
  --path docs/HANDOFF.md \
  --path docs/STATUS.md \
  --path docs/qa/ \
  --mailmap ../mailmap.txt \
  --replace-text ../replacements.txt

git log --all --format='%ae' | sort -u
git log --all -p | grep -c -i -e PERSONAL_GMAIL_ADDRESS -e COMPANY_ACCOUNT_NAME
gitleaks git --log-opts="--all" .
```

Replace the two placeholders with the real strings (kept out of this file on purpose). The two
`git log` checks must show only noreply addresses and a count of 0.

Push: GitHub keeps old commits reachable by SHA and in cached views for a while, even after a
force push. The repo has no forks or pull requests, so either option works:

- **Clean (recommended):** rename the private repo to `homer-archive` (keep it private), create a
  new empty private `Syed-Hamza10/homer`, then `git remote add origin
  git@github-hamza:Syed-Hamza10/homer.git && git push --mirror origin`. The name must stay
  `homer` because `scripts/install.sh` and `homer_core/update.py` use it.
- **In place:** `git remote add origin git@github-hamza:Syed-Hamza10/homer.git && git push
  --force --mirror origin`, then ask GitHub Support to remove cached views and unreachable
  objects before flipping visibility.

Then locally: delete stale worktrees and branches built on the old history (`git worktree list`,
`fix/live-google`, `fix/install-verify`, `docs/readme`, this branch) or rebase their own commits
onto the new `main` with `git rebase --onto`.

## Do before flipping to public

1. Merge the README, installer/onboarding, license and this audit branch into `main`.
2. Copy `docs/launch/`, `docs/HANDOFF.md`, `docs/STATUS.md` to `homer-internal` (the
   `STATUS.md` row in `docs/PROJECT_GUIDE.md` is already removed).
3. Run the history rewrite above and push it (new repo or force push plus GitHub Support).
4. Regenerate or delete the five screenshots with the old privacy line (5.1); delete
   `docs/ui-preview/before/` (5.2).
5. Add a third-party notices file to the wheel, including the Geist OFL text (4.2).
6. Fix the Tavily wording on the site (7.1) and the placeholder contact address (5.5).
7. Note the optional keyed search hosts in `PRIVACY.md` (5.9).
8. Add `dependabot.yml`, narrow `release.yml` permissions (6.2, 6.4).
9. Delete old Actions runs (6.8).
10. Enable private vulnerability reporting, secret scanning and push protection; protect `main`.
11. Re-run `gitleaks git --log-opts="--all" .` on the final mirror, then change visibility.
