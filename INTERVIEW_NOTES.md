# Barak Valley Connect

## Project overview

Barak Valley Connect is a local services platform for Silchar. Visitors can browse provider profiles, search by category/area/skills, and submit service requests. Customers and providers can create accounts. Providers manage their own public listing and see requests for that listing; the website owner manages all listings and requests.

## Application flow

1. `static/index.html` and `static/app.js` present the directory and send JSON requests to FastAPI.
2. `main.py` validates those requests, checks the signed session role, and reads or writes the database through `connect_db()`.
3. `accounts` store customer/provider identity and a PBKDF2 password hash. `service_categories` link to provider rows through `category_id`. `service_requests` reference the selected provider and optionally the signed-in customer.
4. `/providers/{id}` serves the profile page; `static/provider.js` fetches its current public fields from `/api/providers/{id}`.

## Provider matching

The browser sends a short description to `POST /api/recommendations`. The backend fetches current provider names, categories, areas, descriptions, and skills from the database, then calls `matcher.rank_providers()`.

The matcher lowercases and tokenizes text, removes common words, and expands a small set of category vocabulary. It calculates TF-IDF weights and cosine similarity. For each listing, term frequency is `1 + ln(count)`; inverse document frequency is `ln((N + 1) / (df + 1)) + 1`. It ranks matches above a threshold, returns up to three, and includes matching words. The interface displays the cosine score as a percentage but labels it as text similarity, not a probability.

This is an explainable information-retrieval baseline. It is not a trained predictive model or generative AI. It can miss synonyms, misspellings, and multilingual requests. The current tests use a small hand-written sample set; they do not establish broad accuracy.

## A practical example

“My ceiling fan stopped working” is tokenized and compared with each listing profile. The Electrical category profile includes common terms such as “fan,” “wiring,” and “repair.” The match score rises when those weighted terms overlap. The app also returns the overlapping word so a visitor can see why the listing appeared.

## How to test

Install `requirements-test.txt`, then run `python -m unittest -v`. The API tests use temporary SQLite data, including a migration from the earlier database schema. They cover registration/login, role permissions, provider editing/search/profile data, request submission/history, matching, validation, rate limiting, privacy of phone numbers, and existing owner flows.

## Limitations to discuss honestly

- PostgreSQL is supported by the same database adapter, but the local automated suite runs on SQLite. Use a private `DATABASE_URL` to verify a specific PostgreSQL service.
- Provider email verification and password recovery are not implemented.
- There is no payment processing or automatic email/SMS notification.
- The TF-IDF vocabulary and scoring threshold need evaluation against consented, human-labeled requests before relying on recommendation quality at scale.
