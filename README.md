# Barak Valley Connect

A local services platform for finding providers in Silchar and submitting service requests.

## What it does

- Browse and search providers by category, area, business name, description, and skills.
- Open a profile page for each provider.
- Describe a job in plain language and receive up to three ranked provider suggestions with a similarity score and matching words.
- Register as a customer or service provider. Customers can review their requests; providers can edit their own listing and view requests for it.
- Submit a request as a guest or signed-in customer. The website owner can manage listings, requests, and private CSV backups.

Local demo listings are marked **Sample listing · local demo data**. Production starts with an empty directory.

## Stack

- Python, FastAPI, Pydantic, and psycopg
- HTML, CSS, and vanilla JavaScript
- SQLite locally; PostgreSQL when `DATABASE_URL` is set
- TF-IDF and cosine similarity implemented in `matcher.py` using the Python standard library

## Run locally

1. Install Python 3.11 or later.
2. From the project folder, create and activate a virtual environment:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install app dependencies:

   ```sh
   python -m pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`. Set a local `ADMIN_PASSWORD` and a long random `SESSION_SECRET`. Leave `DATABASE_URL` blank for SQLite. To use PostgreSQL, set it to a private connection URL.
5. Start the app:

   ```sh
   python -m uvicorn main:app --reload
   ```

6. Open http://127.0.0.1:8000. The local database creates clearly labeled sample listings. The **Sign in / Create account** button lets you register a customer or provider. The owner signs in separately with `ADMIN_PASSWORD`.

For the automated checks, install test dependencies and run the suite:

```sh
python -m pip install -r requirements-test.txt
python -m unittest -v
```

## Architecture

```text
Browser (static/index.html, app.js, styles.css)
        │ fetch + JSON / signed session cookie
        ▼
FastAPI routes (main.py) ─────── matcher.py (TF-IDF + cosine ranking)
        │ parameterized SQL
        ▼
SQLite for local development / PostgreSQL when DATABASE_URL is set
```

The browser renders provider cards and sends search, account, request, and matching
operations to FastAPI. FastAPI validates incoming JSON with Pydantic, applies role
checks for private operations, and reads or writes provider/account/request rows.
For matching, it loads the current provider records and passes their public listing
text to `matcher.py`; no customer query is stored by the recommendation endpoint.
The same application SQL is used for SQLite and PostgreSQL through a small adapter.

## API overview

Interactive API documentation is available at `/docs` when the app is running.
Authentication uses the signed, HTTP-only session cookie set by the login endpoints.

| Method and path | Access | Purpose |
| --- | --- | --- |
| `GET /health` | Public | Health check including database connectivity |
| `GET /api/auth/me` | Public | Return the current session state |
| `POST /api/auth/register` | Public, rate limited | Register customer or provider; creates a provider listing for provider roles |
| `POST /api/auth/login` / `POST /api/auth/logout` | Public | Sign in or clear the account session |
| `POST /api/auth/admin-login` / `POST /api/auth/admin-logout` | Public | Sign in or clear the website owner session |
| `GET /api/categories` | Public | List categories that have providers |
| `GET /api/providers?category=&area=&q=` | Public | Browse/search listings; phone numbers are hidden |
| `GET /api/providers/{id}` | Public; owner/listing owner may see phone | View a provider profile |
| `POST /api/recommendations` | Public, rate limited | Rank live listings against a short natural-language request |
| `POST /api/requests` | Public, rate limited | Submit a request with explicit privacy consent |
| `GET /api/my/requests` | Customer | View requests owned by the signed-in customer |
| `GET /api/provider/profile` / `PUT /api/provider/profile` | Provider | Read or update only the signed-in provider's listing |
| `GET /api/provider/requests` | Provider | View requests for only that provider's listing, including contact needed to respond |
| `GET /api/requests`, `PATCH /api/requests/{id}/status`, `DELETE /api/requests/{id}` | Website owner | Manage service requests |
| `GET /api/summary`, `GET /api/admin/requests.csv` | Website owner | View counts or download a private CSV backup |
| `POST /api/providers`, `PUT /api/providers/{id}`, `DELETE /api/providers/{id}` | Website owner | Manage directory listings |

## How provider matching works

1. The app tokenizes the requirement and each current listing into lowercase words,
   removing common and overly generic words. A small curated synonym map handles
   local-service vocabulary such as `faucet`/`tap` and `hedges`/`pruning`; a
   conservative close-word correction handles common typos.
2. It builds a term-frequency vector for the query and each listing. Each term is
   weighted with smoothed inverse document frequency:
   `idf(t) = ln((N + 1) / (df(t) + 1)) + 1`. A term that distinguishes one listing
   matters more than a word present in every listing.
3. It normalizes the vectors and computes cosine similarity:
   `cos(q, d) = (q · d) / (||q|| × ||d||)`. Results below the implementation's
   minimum relevance threshold are omitted; remaining rows are sorted by score and
   name, and the top three are returned with overlapping terms as explanations.

The displayed score is text similarity on this current directory, not a probability,
quality rating, or endorsement. This baseline does not understand sentence meaning,
language beyond its English vocabulary, availability, distance, price, or provider
quality. Keep provider descriptions and skills accurate; add synonyms only when they
reflect real service vocabulary, and verify ranking changes with the API query cases.

## Interview walkthrough

Describe the project as a small full-stack marketplace with a transparent retrieval
baseline. A customer submits a short requirement; the FastAPI endpoint validates it,
loads actual provider listings from the database, then uses TF-IDF to represent query
and listing text and cosine similarity to rank them. The interface shows the score
and matched terms, and the API returns a clear no-match response when nothing clears
the threshold. You can explain the tradeoff: this is inexpensive, deterministic, and
inspectable for a small directory, but it misses semantic equivalence; a future
evaluation could compare this baseline with a multilingual embedding model using
human-labeled query/provider relevance pairs. Scores must not be described as
confidence or probabilities.

The checks cover customer/provider registration and login, role-scoped endpoints,
profile updates, category filters, request creation and history, SQLite persistence
after reopening the app, additive migration safety, security headers and production
configuration validation. Thirty-six realistic provider-matching queries use rows in
an isolated test database; the cases include common spelling variations, curated
synonyms and unrelated requests that should return no suggestions.

## Data and privacy

The database contains `accounts`, `service_categories`, `providers`, `service_requests`, and `rate_limit_buckets`. Provider categories and customer requests link through database IDs. Startup creates missing tables and applies the current additive column migrations; PostgreSQL startup workers serialize this step with a transaction-scoped advisory lock. Rate limits use an atomic database upsert, so limits are shared across workers and survive app restarts. Fixed windows can allow a short burst across a window boundary.

Passwords are stored as PBKDF2 hashes. Public listings do not show provider phone numbers. The matching request is processed by this app, is not saved, and is not sent to an outside AI service. The privacy page explains which account and service-request details are stored and who can view them.

## Deployment

`render.yaml` defines both the Python web service and a PostgreSQL resource in Singapore. Its `DATABASE_URL` references the database's private connection string, and the database allowlist blocks external connections. The database is created only when you create or sync this Blueprint in Render; editing this file or pushing the branch does not provision it. Production startup rejects SQLite URLs and `/health` checks the database connection.

For a Render launch, first review the PostgreSQL plan and billing shown in Render before syncing the Blueprint. The Blueprint currently omits a database plan, so Render applies its default plan for a new database. Confirm these environment variables in Render's private settings:

- `APP_ENV=production`
- `DATABASE_URL`: automatically supplied from the Blueprint database resource; for an existing external database instead, change this to a private `sync: false` value and remove or reuse the declared database resource before syncing
- `SESSION_SECRET`: at least 32 random characters; the blueprint requests a generated value
- `ADMIN_PASSWORD`: at least 16 characters
- `SITE_OPERATOR_NAME` and `PRIVACY_CONTACT_EMAIL`: real contact details for the privacy notice
- `REQUEST_RETENTION_DAYS`: positive integer, such as `30`

The service build command is `pip install -r requirements.txt`, the start command is `uvicorn main:app --host 0.0.0.0 --port $PORT`, and Render checks `/health`. After configuring contacts and the owner password and approving the database plan, verify `/health`, account registration/login, provider listing, matching, and request persistence against PostgreSQL. Do not put database URLs or passwords in Git.

The account and matching changes are on the `codex/final-barak-valley-connect` branch and in draft PR #2. They have not been merged or deployed. The existing live URL may still be running the previous version. PostgreSQL and Render deployment should be checked with the intended private connection settings before publishing.

## Current limits

The matcher is a small information-retrieval baseline. It uses word overlap,
curated category vocabulary, a small synonym map, conservative close-spelling
correction, TF-IDF, and cosine similarity. Its score is not a probability or an
endorsement. It does not understand sentence meaning, and it can miss unlisted
synonyms, complex misspellings, and multilingual requests. Matching quality depends
on providers maintaining useful descriptions and skills. Provider accounts are not
email-verified, and the app does not include password recovery, payments, or
automatic email/SMS notifications.

Rate-limit counters use an HMAC keyed by the session secret rather than storing raw
IP addresses. Counters are removed within 24 hours. Use a stable, private session
secret in production so rate limits remain consistent across app workers. The local
verification uses SQLite and an isolated test database. A live PostgreSQL connection,
physical mobile device, and deployed Render service were not available for this check,
so those environments remain unverified. The current changes are in draft PR #2 and
have not been deployed.

Schema creation and additive upgrades currently run at startup; they are not tracked
by a versioned migration tool and do not provide automatic rollback. Back up an
existing database before production upgrades and review schema changes before release.
