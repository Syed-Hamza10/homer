# Connecting a Google account

Use a throwaway Gmail account for development. Never connect your main account until the client's
own account is set up the same way. Everything below is done once; it takes about fifteen minutes.

## 1. Create the throwaway Gmail account

1. Open a private browser window and go to `https://accounts.google.com/signup`.
2. Pick a name and an address you will not use for anything else (for example `homer.dev.<something>@gmail.com`), set a password, finish the sign-up.
3. Stay signed in to this account for every step below.

## 2. Create a Google Cloud project

1. Go to `https://console.cloud.google.com/`. Accept the terms when asked.
2. Click the project picker at the top left, then **New project**.
3. Name it `homer-dev`, leave the organisation empty, click **Create**, then select it in the picker.

## 3. Enable the three APIs

1. Open **APIs & Services → Library** from the left menu.
2. Search `Gmail API`, open it, click **Enable**.
3. Go back to the Library and do the same for `Google Calendar API` and `People API`.

## 4. Set up the OAuth consent screen

1. Open **APIs & Services → OAuth consent screen** (Google now calls this **Google Auth Platform → Branding**). Click **Get started**.
2. App name `Homer`, user support email: the throwaway address. Click **Next**.
3. Audience: **External**. Click **Next**. Contact email: the throwaway address. Agree, **Create**.
4. Open **Audience** in the left menu. The publishing status must say **Testing**. Under **Test users** click **Add users**, enter the throwaway address, **Save**.
5. Open **Data access** and click **Add or remove scopes**. Tick `.../auth/gmail.modify`, `.../auth/calendar` and `.../auth/contacts.readonly` (filter the list by typing the name), click **Update**, then **Save**.

## 5. Create a Desktop OAuth client

1. Open **Clients** (or **APIs & Services → Credentials**), click **Create client** / **Create credentials → OAuth client ID**.
2. Application type **Desktop app**, name `Homer desktop`, click **Create**.
3. In the dialog, click **Download JSON**. Save the file as `client_secret.json`.
4. Move it into place and lock it down:

   ```sh
   mkdir -p ~/.homer/credentials
   mv ~/Downloads/client_secret*.json ~/.homer/credentials/client_secret.json
   chmod 600 ~/.homer/credentials/client_secret.json
   ```

## 6. Run the one-time consent flow

1. On an installed machine, open Settings. The Google account card checks for the file from step 5; if it says the OAuth client is missing, save the file at the path it shows and press **Check again**.
2. Press **Sign in with Google**. Homer does not open a browser; it shows a sign-in link with **Copy link** and **Open** buttons.
3. Copy the link and open it in a private/incognito window, then sign in with the throwaway account. Google answers "400. That's an error ... malformed" when the normal browser is signed into several Google accounts at once; a private window avoids it.
4. Google warns that the app is unverified: click **Continue**. Tick all three permissions, click **Continue**.
5. The private window says the flow is complete and can be closed. Settings changes to **Connected as** the account's address within a few seconds. The token is at `~/.homer/credentials/google_token.json`, mode 0600; the server reads it and refreshes the access token on its own.
6. Start the app and open the Privacy page: `www.googleapis.com`, `oauth2.googleapis.com` and `people.googleapis.com` are the only Google hosts that should ever appear.

From a terminal instead: `~/.homer/venv/bin/homer setup google`, or from the repo `uv run homer-mcp-google-setup`. That opens the sign-in page in the default browser and prints `Google connected. Token written to ...` when done. Add `--no-browser` to `homer-mcp-google-setup` to print the link instead, then open it in a private window.

## The 7-day rule

While the consent screen is in **Testing**, Google expires the refresh token after 7 days. From day 5
the Today page and `homer doctor` warn; once it expires the chat answers "Your Google connection has
expired". Press Reconnect in Settings, which shows the same sign-in link as step 6 (or run `uv run homer-mcp-google-setup` again). Moving the app to **In production** removes the limit but
needs Google's verification review, which is a step for the real client account, not the throwaway.
