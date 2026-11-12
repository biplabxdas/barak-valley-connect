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

The checks cover customer/provider registration and login, role-scoped endpoints,
profile updates, category filters, request creation and history, SQLite persistence
after reopening the app, and 31 realistic provider-matching queries against rows in
an isolated test database. The query set includes common spelling variations and
unrelated requests that should return no suggestions.

## Data and privacy

The database contains `accounts`, `service_categories`, `providers`, `service_requests`, and `rate_limit_buckets`. Provider categories and customer requests link through database IDs. Startup creates missing tables and applies the current additive column migrations; PostgreSQL startup workers serialize this step with a transaction-scoped advisory lock. Rate limits use an atomic database upsert, so limits are shared across workers and survive app restarts. Fixed windows can allow a short burst across a window boundary.

Passwords are stored as PBKDF2 hashes. Public listings do not show provider phone numbers. The matching request is processed by this app, is not saved, and is not sent to an outside AI service. The privacy page explains which account and service-request details are stored and who can view them.

## Deployment

`render.yaml` configures the Python web service, start command, and database-backed `/health` check; it does not provision a PostgreSQL database. Create or select a PostgreSQL database first, then set its private connection URL as `DATABASE_URL` for the web service. Production startup rejects SQLite URLs and checks the database with `/health`.

For a Render launch, create a PostgreSQL database in the same region where possible, then create the web service from this repository and select `codex/final-barak-valley-connect` only after deciding to publish that branch. Confirm these environment variables in Render's private settings:

- `APP_ENV=production`
- `DATABASE_URL`: private PostgreSQL connection URL from the database provider
- `SESSION_SECRET`: at least 32 random characters; the blueprint requests a generated value
- `ADMIN_PASSWORD`: at least 16 characters
- `SITE_OPERATOR_NAME` and `PRIVACY_CONTACT_EMAIL`: real contact details for the privacy notice
- `REQUEST_RETENTION_DAYS`: positive integer, such as `30`

The service build command is `pip install -r requirements.txt`, the start command is `uvicorn main:app --host 0.0.0.0 --port $PORT`, and Render checks `/health`. After configuring credentials and publishing, verify `/health`, account registration/login, provider listing, matching, and request persistence against the selected database. Do not put database URLs or passwords in Git.

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
