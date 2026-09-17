# Hougang ActiveSG Gym — Capacity Tracker

Hourly-polling dashboard for Hougang ActiveSG Gym crowd data, built on:
- **GitHub Actions** — runs `scripts/poll.py` every hour, hits the (unofficial)
  ActiveSG capacity endpoint, appends to `data/capacity.csv`, and rebuilds
  `docs/data.json`.
- **GitHub Pages** — serves `docs/index.html`, a static dashboard that reads
  `docs/data.json` and shows the quietest hours + recent trend.

## ⚠️ Risk / reliability notes
- The endpoint (`activesg.gov.sg/api/trpc/pass.getFacilityCapacities`) is
  undocumented and reverse-engineered from the browser's Network tab — it
  could change shape or start rejecting requests at any time. The poller logs
  failures instead of crashing, and still rebuilds the dashboard from
  existing data so the site doesn't break on a bad run.
- Polling once an hour is intentionally light — no need to go more frequent.
- No credentials/secrets are involved; this only reads public data.

## Setup

1. **Create the repo.** On GitHub, create a new (public) repo, e.g.
   `hougang-gym-capacity`. Don't initialize it with a README (this project
   already has one).

2. **Push this project:**
   ```bash
   cd hougang-gym-capacity
   git init
   git add .
   git commit -m "Initial commit: hourly capacity poller + dashboard"
   git branch -M main
   git remote add origin https://github.com/<your-username>/hougang-gym-capacity.git
   git push -u origin main
   ```

3. **Allow the Action to push commits.**
   Repo → **Settings → Actions → General → Workflow permissions** → select
   **"Read and write permissions"** → Save.
   (Without this, the workflow can poll but can't commit the data back.)

4. **Enable GitHub Pages.**
   Repo → **Settings → Pages** → Source: **Deploy from a branch** → Branch:
   `main`, folder: `/docs` → Save.
   Your dashboard will be live at:
   `https://<your-username>.github.io/hougang-gym-capacity/`

5. **Kick off the first run manually** (don't wait for the hourly cron):
   Repo → **Actions** tab → **Poll Hougang Gym Capacity** → **Run workflow**.
   After it finishes (~30s), `data/capacity.csv` and `docs/data.json` will
   have their first row, and the Pages site will show it within a minute or
   two of the next Pages deployment.

6. From then on, it runs automatically every hour — no maintenance needed.
   Give it a few days and the "quietest hours" panel will start being
   genuinely useful.

## Local testing (optional)

```bash
python3 scripts/poll.py
```
Appends a row to `data/capacity.csv` and rewrites `docs/data.json` locally,
so you can open `docs/index.html` in a browser to preview.

## Tracking a different gym

Open `scripts/poll.py` and change `FACILITY_ID` / `FACILITY_NAME` — the
`gymFacilities` array in the API response includes every ActiveSG gym's ID
and name if you want to adapt this for another location.
