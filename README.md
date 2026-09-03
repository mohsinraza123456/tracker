# Tracker

A self-hosted performance-marketing click tracker (à la CPV Lab): track clicks
from traffic sources through optional landing pages to offers, record
conversions via pixel or server-to-server postback, and see cost/revenue/ROI
per campaign.

## Setup

1. Start Postgres:

   ```bash
   docker compose up -d
   ```

2. Install dependencies (already done if you ran this via the assistant):

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set `ADMIN_USERNAME`/`ADMIN_PASSWORD`
   (the dashboard login) and a fixed `SECRET_KEY` — generate one with
   `python -c "import secrets; print(secrets.token_hex(32))"`. Without a
   pinned `SECRET_KEY`, a new random one is generated on every restart and
   everyone gets logged out.

4. Run the app:

   ```bash
   uvicorn app.main:app --reload
   ```

   The app runs `alembic upgrade head` on startup, so the database schema is
   always brought up to date automatically — no manual migration step needed.

5. Open http://localhost:8000

## Schema changes

The schema is managed with [Alembic](https://alembic.sqlalchemy.org)
(`alembic/versions/`), not by hand-editing the database. After changing a
model in `app/models.py`:

```bash
python -m alembic revision --autogenerate -m "describe the change"
```

Review the generated file in `alembic/versions/` (autogenerate doesn't always
get everything right — check column types, defaults, and data backfills for
existing rows), then restart the app to apply it, or run
`python -m alembic upgrade head` directly.

## How it works

- **Login**: the dashboard and all admin pages require a login
  (`ADMIN_USERNAME`/`ADMIN_PASSWORD` from `.env`, default `admin`/`admin` if
  unset — change this before running anywhere but your own machine). The
  tracking endpoints (`/click`, `/go`, `/conv`, `/postback`) stay public since
  traffic sources and offers need to hit them without a session.
- **Traffic Sources**: where clicks come from, with a cost model (manual or
  cost-per-click).
- **Landing Pages** (optional): pre-landers. On the landing page, link onward
  to `{base_url}/go/{clickid}` to hand the visitor to the offer.
- **Offers**: the final destination and its payout. Use the token `{clickid}`
  in the offer URL if it needs to be embedded in the path, otherwise it's
  appended as `?clickid=`.
- **Campaigns**: combine a traffic source + a weighted rotation of offers
  (and optionally landing pages) into one trackable link:
  `{base_url}/click/{campaign_id}`. Put that link at your traffic source (ad
  network, email, etc.), optionally with `?sub1=...&sub2=...` custom
  parameters.
- **Split testing**: give two or more offers (or landing pages) a weight > 0
  on a campaign and the tracker rotates visitors across them by weight —
  equal weights split evenly, uneven weights (e.g. 70/30) send more traffic
  to one variant. Each click records which offer/landing page it actually
  got, so the campaign page and Reports (`Breakdown by: Offer` /
  `Landing Page`) show clicks/conversions/ROI per variant to see which wins.
- **Conversions**: fire one of these when a visitor converts on the offer
  side, passing back the `clickid` that was appended to the offer URL:
  - Pixel: `GET {base_url}/conv/{clickid}?payout=1.23&txid=abc`
  - Postback (S2S): `GET {base_url}/postback?clickid={clickid}&payout=1.23&txid=abc`

  `payout` defaults to the offer's default payout if omitted. `txid` is an
  optional external id used to dedupe repeated postbacks.
- **Bot/duplicate filtering**: every click is checked for a bot-like
  User-Agent (known crawlers, headless browsers, `curl`/`wget`/script
  clients, or no User-Agent at all) and for repeats — the same
  campaign+IP+User-Agent within `DEDUPE_WINDOW_SECONDS` (default 10s) is
  treated as a double-click/reload rather than a new visitor. Both kinds are
  still recorded (visible in the campaign's click log, flagged `Bot`/`Dup`)
  but excluded from every stats view and from cost, so they can't inflate
  click counts or corrupt split-test ROI. A duplicate click reuses whichever
  offer/landing page the original click got, so a real visitor double-clicking
  never gets bounced to a different split-test variant.
