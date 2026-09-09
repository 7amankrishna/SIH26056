# Setup guide — APIx live scraper on Vercel + Supabase

Plain-language, click-only instructions. No terminal, no commands.

For a durable scraper you need three things, all free (Supabase is optional
for the temporary-store demo):

| Thing | What it does | Where |
| --- | --- | --- |
| **GitHub** | holds the code | github.com (already done) |
| **Vercel** | runs the website + API | vercel.com (already done) |
| **Supabase** | the database that remembers what the scraper collected | supabase.com (5 minutes, below) |

> **Do you even need Supabase?** No — the scraper works without it. Without a
> database it stores collected fares in the function's temporary disk (`/tmp`).
> Vercel ignores `DATABASE_URL` by default, including leftover/broken values.
> This temporary store is wiped whenever Vercel restarts the function (a "cold
> start") or you redeploy. That is fine for a live demo, and the dashboard labels it
> **"Ephemeral collection store (serverless /tmp)"** so nobody is misled.
> Add Supabase when you want the collected history to **survive** — days of
> sweeps building up a real index, which is the far more convincing demo.

---

## Step 1 — Create the Supabase project (2 min)

1. Go to <https://supabase.com> → **Sign in** (GitHub login is easiest).
2. **New project**.
3. Fill in:
   - **Name**: `apix` (anything you like)
   - **Database Password**: click *Generate a password* → **copy it somewhere safe now**.
     You will paste it into Vercel in Step 3. If you lose it you can reset it later
     in *Project Settings → Database → Database password*.
   - **Region**: pick the one closest to you (for India: *South Asia (Mumbai)*).
   - **Plan**: Free.
4. **Create new project** and wait ~2 minutes for it to finish setting up.

## Step 2 — Create the tables (1 min)

1. In your Supabase project, left sidebar → **SQL Editor**.
2. Click **+ New query**.
3. Open the file [`db/supabase_schema.sql`](../db/supabase_schema.sql) in this
   repository (on GitHub: click the file → **Raw** → select all → copy).
4. Paste the whole file into the SQL Editor.
5. Click **Run** (bottom-right).
6. You should see **"Success. No rows returned."**

That created five tables: `observations` (the fares), `raw_payloads` (the bytes
exactly as received), `collection_runs` (the run log), `apix_state` (remembers
your Demo/Scraper switch) and `schema_meta`. It also turned on **Row Level
Security**, which means nobody can read or write these tables through Supabase's
public web API with an anonymous key — only your backend, using its own database
login, can touch them.

You can look at the data any time: left sidebar → **Table Editor**.

> Running the file again is harmless — it is written to be idempotent.

## Step 3 — Give Vercel the database address (2 min)

You need the connection string (`DATABASE_URL`) and an explicit opt-in
(`APIX_IGNORE_DATABASE_URL=0`). Without the opt-in, Vercel uses the temporary
SQLite store even if a database address is already configured.

1. Supabase → **Project Settings** (the gear icon, bottom-left) → **Database**.
2. Find **Connection string** (also called *Connection pooling*). Choose the
   **Transaction pooler** (port `6543`) — that is the one designed for
   serverless platforms like Vercel.
3. Copy the URI. It looks like this (yours will have your own project reference):

   ```
   postgresql://postgres.abcdefghijklmnop:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
   ```

4. Edit it into its final form:
   - Replace `[YOUR-PASSWORD]` with the password from Step 1.
   - It **must start with `postgresql://`** (or `postgres://`).
   - Add `?sslmode=require` at the very end if it is not already there:

   ```
   postgresql://postgres.abcdefghijklmnop:MyRealPassword123@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require
   ```

   > If your password contains any of these characters — `@ : / ? # [ ] %` —
   > it must be URL-encoded (for example `@` becomes `%40`). Supabase's generated
   > passwords are letters and digits, so this rarely matters.

5. Now Vercel: <https://vercel.com> → **Dashboard** → your project →
   **Settings** → **Environment Variables**.
6. Add:
   - **Name**: `DATABASE_URL`
   - **Value**: the string from step 4
   - **Environment**: tick **Production**, **Preview** and **Development**
   - **Save**
7. **Important:** if `DATABASE_URL` already exists there with a different value,
   **edit/replace it** — do not add a second one. (A leftover value that is not a
   PostgreSQL address produces `DATABASE_URL must be a PostgreSQL connection
   URL` once PostgreSQL is enabled.)
8. Add a second environment variable in the same three environments:
   - **Name**: `APIX_IGNORE_DATABASE_URL`
   - **Value**: `0`
   - **Save**
   This enables PostgreSQL. To return to the temporary-store demo, set it to `1`
   (or delete this opt-in) and redeploy; you need not edit `DATABASE_URL`.
9. Environment variables only apply to a **new** deployment:
   **Deployments** → the newest one → **⋯** (three dots) → **Redeploy**.

## Step 4 — Deploy the fixed code (1 min)

Deploy the latest `main`, which contains the serverless scraper fixes, the
ignore-`DATABASE_URL` default, this guide and the Supabase schema.

1. GitHub → the repository → **Pull requests** → merge the latest scraper fix
   into `main` if it has not already been merged.
2. Vercel watches the `main` branch, so it builds and deploys automatically —
   watch **Deployments** until the newest one says *Ready*.
3. If you earlier promoted a preview deployment to production, merging `main`
   simply replaces it with the same code — nothing to undo.
4. Env variables added *after* a deployment need one more deploy to take effect:
   **Deployments** → newest → **⋯** → **Redeploy**.

## Step 5 — Check it worked (1 min)

1. Open `https://<your-vercel-url>/api/health` in a browser tab. You want:

   ```json
   "store_backend": "postgresql",
   "store_available": true,
   "request_scoped_runtime": true
   ```

2. Open the dashboard and flip the switch (top-right) from **Demo data** to
   **Scraper**. Within a second or two the header badge changes to
   `LIVE · SCRAPED DATA` and the numbers on every screen change.
3. Open **Live Feed (Scraper)** in the sidebar. You should see:
   - a chip saying **sweeps run in-request** (normal on Vercel — there is no
     background loop there, so a sweep runs inside the request that asks for it);
   - **Observations stored / Index-eligible / Raw payloads archived** greater than 0;
   - **no** amber "ephemeral store" banner any more (that banner only appears when
     the store is the temporary `/tmp` one);
   - the run log with a green **success** row.
4. Press **Run sweep now** — a new row appears in the run log and the counts grow.
5. Go back to Supabase → **Table Editor** → `observations`: the same rows are there.
   That is the proof the data is durable now.
6. Redeploy or wait an hour, then look again: with Supabase the data is still there.
   (With `/tmp` it would be gone — that is the whole difference.)

---

## Which environment variables do I need on Vercel?

**Required for a durable scraper — two settings:**

| Name | Value | Why |
| --- | --- | --- |
| `APIX_IGNORE_DATABASE_URL` | `0` | opts in to PostgreSQL instead of the Vercel temporary-store default |
| `DATABASE_URL` | the Supabase connection string from Step 3 | where collected fares, raw payloads and run logs are stored |

**Optional (the defaults are already right for a demo):**

| Name | Default | Set it when… |
| --- | --- | --- |
| `APIX_COLLECTOR_SOURCES` | `fixture` | you want a different source: `fixture_html` (scrapes an HTML *page* with CSS selectors — the best jury demo), `amadeus` (real permissioned airline API), `http_json` / `http_html` (a source whose terms allow automation). Multiple: `fixture,fixture_html` |
| `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET` | *(empty)* | you chose `amadeus`. Get them free at <https://developers.amadeus.com> |
| `APIX_DATA_MODE` | *(unset)* | set to `demo` to **lock** the dashboard on the reproducible synthetic dataset for the jury presentation (the switch then shows *locked*). Set to `live` to lock it on scraped data. Leave unset to keep the switch usable |
| `APIX_DEMO_DAYS` | `90` | you want a longer/shorter synthetic history |
| `APIX_MIN_REQUEST_GAP_SECONDS` | `2.0` | politeness delay between requests to a real website. Never lower it for a third-party host |
| `APIX_REQUEST_SWEEP_BUDGET_SECONDS` | `45` | how long an in-request sweep may take. Keep it below the function timeout (`maxDuration: 60` in `vercel.json`) |
| `APIX_SWEEP_ROUTES` | *(all 24)* | you want a sweep to cover only e.g. `DEL-BOM,DEL-MAA` |
| `APIX_SWEEP_LEAD_TIMES` | `1,7,30` | you want different advance-booking windows |
| `APIX_COLLECTOR_ENABLED` | auto (`0` on Vercel) | leave alone on Vercel — a background loop cannot survive there. Set `1` only on Docker/VM deployments |
| `APIX_DATA_DIR` | auto (`/tmp/apix-data` on Vercel) | used when `DATABASE_URL` is ignored or unset |
| `APIX_CUSTOM_DATA_DIR` | `<repo>/data` | where **your** fare exports live. Drop a CSV/JSON there and it replaces the demo dataset; drop another and the rows merge in. See `data/README.md` |
| `APIX_CUSTOM_DATA` | `1` | set `0` to ignore those files and go back to the synthetic dataset |

When you enable PostgreSQL, **do not set** `DATABASE_URL` to a MySQL, SQLite,
Redis, or `https://…` address — anything that is not PostgreSQL is refused on
purpose. While `APIX_IGNORE_DATABASE_URL=1` (the Vercel default), the value is
not read, validated or connected to, and the API/UI explicitly label the SQLite
store as temporary. Switching backends does not migrate existing history.

---

## Troubleshooting — the exact message tells you the fix

| You see | What it means | Fix |
| --- | --- | --- |
| `Cannot serve scraped data: the collection store is unavailable. DATABASE_URL must be a PostgreSQL connection URL.` | `APIX_IGNORE_DATABASE_URL=0` enables `DATABASE_URL`, but it is not a PostgreSQL address (it starts with `https://`, `mysql://`, or is a placeholder) | Replace it with the Supabase URI from Step 3, or set `APIX_IGNORE_DATABASE_URL=1` for the temporary demo, then **Redeploy** |
| `… DATABASE_URL is not a valid PostgreSQL DSN.` / `… must specify a database.` | the string was pasted incompletely (usually the `/postgres` database name at the end is missing) | copy the whole URI again, ending in `/postgres?sslmode=require` |
| `Collection store unavailable: PostgreSQL is configured but could not be reached: OperationalError` | wrong password, wrong host/port, project paused, or you used the IPv6-only direct connection | use the **Transaction pooler** URI (port `6543`), re-check the password, and make sure the Supabase project is *Active* (free projects pause after ~1 week idle — open the Supabase dashboard to restore) |
| `/api/health` shows `"store_backend": "sqlite"` and the Live Feed shows an amber **Ephemeral collection store (serverless /tmp)** banner | `DATABASE_URL` is ignored (the Vercel default) or unset | Works for a demo, but data resets on cold start. For durability, set both `APIX_IGNORE_DATABASE_URL=0` and the PostgreSQL URI from Step 3, then redeploy |
| `409 No collection adapter is enabled` | `APIX_COLLECTOR_SOURCES` was set to something empty or misspelled | set it to `fixture` (or delete the variable — `fixture` is the default) |
| The switch flips back to **Demo data** by itself, with a note that the store is empty | live mode was asked for but nothing has been collected yet | press **Run sweep now** once; the switch then stays on Scraper |
| Everything says *demo* and the switch shows **locked** | `APIX_DATA_MODE` is set on Vercel | delete that variable (or set it to the mode you want) and redeploy |
| Live Feed shows a source as **blocked** with a circuit-breaker message | that source refused automated access, and the engine stopped and backed off — by design | leave it; the engine never works around a refusal. Use an authorized source (`fixture`, `fixture_html`, `amadeus`) |
| Old behaviour: `Internal Server Error` on `/api/health`, `/api/data-source`, `/api/collect/status` | you are running the code **before** PR #7 | merge PR #7 and redeploy |

---

## What to say to the jury about this

> "The collector runs on the same code path everywhere. On Vercel there is no
> process lifetime between requests, so a sweep runs *inside* the request that
> asks for it and the result is returned to the dashboard in one round trip.
> Storage defaults to a clearly-labelled temporary SQLite store on Vercel;
> with an explicit opt-in and a valid database address it uses PostgreSQL on
> Supabase for durable history. If a
> source refuses automated access, the run is recorded as **blocked** and the
> circuit breaker opens — the engine has no CAPTCHA solving, no fingerprint
> rotation and no way around a `robots.txt` denial, and that is deliberate:
> a fare series feeding a statistical index has to be collectable in the open."

See also [Scraping / collection policy](SCRAPING_POLICY.md) and
[Deployment](DEPLOYMENT.md).
