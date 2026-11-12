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

The database contains `accounts`, `service_categories`, `providers`, and `service_requests`. Provider categories and customer requests link through database IDs. Existing SQLite and PostgreSQL provider/request tables are extended during startup so older databases keep their records.

Passwords are stored as PBKDF2 hashes. Public listings do not show provider phone numbers. The matching request is processed by this app, is not saved, and is not sent to an outside AI service. The privacy page explains which account and service-request details are stored and who can view them.

## Deployment

`render.yaml` configures the Render web service. Production requires `DATABASE_URL`, `SESSION_SECRET`, `ADMIN_PASSWORD` (at least 16 characters), `SITE_OPERATOR_NAME`, `PRIVACY_CONTACT_EMAIL`, and `REQUEST_RETENTION_DAYS` (a positive number). Keep secrets in Render's private environment settings, not in this repository.

The project copy includes local changes that have not been pushed or deployed. The live URL, if available, may still be running the previous version. PostgreSQL and Render deployment should be checked with the intended private connection settings before publishing.

## Current limits

The matcher is a small information-retrieval baseline. It uses word overlap,
curated category vocabulary, a small synonym map, conservative close-spelling
correction, TF-IDF, and cosine similarity. Its score is not a probability or an
endorsement. It does not understand sentence meaning, and it can miss unlisted
synonyms, complex misspellings, and multilingual requests. Matching quality depends
on providers maintaining useful descriptions and skills. Provider accounts are not
email-verified, and the app does not include password recovery, payments, or
automatic email/SMS notifications.

The local final verification used SQLite and an isolated test database. A live
PostgreSQL connection, physical mobile device, and deployed Render service were not
available for this check, so those environments remain unverified. No changes were
pushed to GitHub and no deployment was made.
