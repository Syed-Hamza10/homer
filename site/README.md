# Homer landing page

One static file, `index.html`, with inline CSS and a small inline script. No build step, no
external scripts, no fonts from a CDN, no analytics. Light and dark mode follow the visitor's
system setting.

## Files

| File | Required | What it is |
|---|---|---|
| `index.html` | yes | The page |
| `demo.mp4` | no | The demo video. When it is present, the page swaps the placeholder for a video player. |
| `demo-poster.jpg` | no | The video's poster frame (a still from the first second). |

Until `demo.mp4` exists the hero shows a "Demo video, coming soon" placeholder. The check is a
`HEAD` request, so it only works over HTTP, not when the file is opened from disk.

## Preview locally

```sh
cd site && python3 -m http.server 8000
```

Open http://localhost:8000.

## Deploy for free

Any static host works. Three that need no account setup beyond sign-in:

- **GitHub Pages.** Put the contents of `site/` in a public repository (for example `homer-site`),
  then Settings > Pages > Deploy from a branch > `main` / root. The page is live at
  `https://<user>.github.io/homer-site/` within a minute. Pages on a free plan needs a public repo,
  so do not publish the main Homer repository this way.
- **Cloudflare Pages.** Workers & Pages > Create > Pages > Upload assets, then drag the `site/`
  folder in. You get a `*.pages.dev` address and can add your own domain later.
- **Netlify.** Open https://app.netlify.com/drop and drag the `site/` folder onto it. You get a
  `*.netlify.app` address.

Videos over 25 MB may hit per-file limits on some hosts (Cloudflare Pages caps files at 25 MiB).
Export the demo at 1080p, H.264, under 25 MB, or host it elsewhere and point `DEMO_VIDEO` at it.

## The waitlist form

The top of the inline script has the settings:

```js
const WAITLIST_ENDPOINT = "";
const CONTACT_EMAIL = "syed.hamza.ds@gmail.com";
const DEMO_VIDEO = "demo.mp4";
const DEMO_POSTER = "demo-poster.jpg";
```

The form checks the email, role and firm size in the browser, then:

- **When `WAITLIST_ENDPOINT` is empty (the default):** it opens the visitor's email app with a
  pre-filled message to `CONTACT_EMAIL` and shows a success note telling them to press Send.
  Keep the footer link in `index.html` in step with `CONTACT_EMAIL`.
- **When `WAITLIST_ENDPOINT` is set:** it sends `POST` with
  `Content-Type: application/json` and the body `{"email": "...", "role": "...", "firm_size": "..."}`.
  Any 2xx response shows the success state; anything else shows an error with the contact address.

### Plugging in a backend

- **Formspree.** Create a form, copy its endpoint (`https://formspree.io/f/<id>`) into
  `WAITLIST_ENDPOINT`. Formspree accepts JSON when the `Accept: application/json` header is sent,
  which the page does. Free tier: 50 submissions a month.
- **Your own endpoint.** Any URL that accepts the JSON above and returns 2xx. If it is on another
  domain, it must answer CORS preflight (`OPTIONS`) and allow `Content-Type`. A Cloudflare Worker or
  a Netlify Function writing to a sheet or a database is about 20 lines.
- **Tally or Google Forms.** These do not accept JSON posts from another site. Either leave the
  endpoint empty and link the form instead (replace the `<form>` block with a button pointing at
  the Tally or Google Form URL), or embed their iframe in place of the form. Both add the provider's
  scripts to the page, so update the "no tracking scripts" line under the form if you do.

## Before launch

- Confirm `syed.hamza.ds@gmail.com` in the script and the footer is the inbox you want public.
- Add `demo.mp4` and `demo-poster.jpg` once the video is recorded.
- Re-read every claim against `docs/CASE_STUDY.md` if the product changes. The page uses only
  numbers from there and from the QA logs.
