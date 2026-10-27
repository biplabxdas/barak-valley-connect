# Local Business Management & Service Platform

A browser website for a small local service directory. Development mode includes sample Silchar businesses; production mode starts with an empty database and should be populated only with businesses that agreed to be listed.

## What it does

- Lists local service providers and filters them by service category.
- Adds, edits, and removes providers from the web page.
- Lets a customer submit a service request.
- Shows recent requests and lets the demo user change their status.
- Shows simple totals for providers, requests, pending work, and completed work.
- Saves local development data in SQLite; public hosting uses a Supabase PostgreSQL database.
- Provides interactive API documentation at `/docs`.

## Run it on macOS

1. Install Python 3 if it is not already installed: <https://www.python.org/downloads/macos/>.
2. Open Terminal and go to this project folder.
3. Create and activate a project-only environment:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install the app packages and start the website:

   ```sh
   python -m pip install -r requirements.txt
   python -m uvicorn main:app --reload
   ```

5. Open <http://127.0.0.1:8000> for the website or <http://127.0.0.1:8000/docs> to try each API route.
6. Stop the local server with Control+C in Terminal.

In local development, the owner sign-in password is `local-demo-password`. This is a demo-only password; never use it on a public website.

For a private local password, copy `.env.example` to `.env`, set a unique `ADMIN_PASSWORD` and a long random `SESSION_SECRET`, then restart the server. `.env` is excluded from GitHub.

The first launch creates `business.db` and inserts three demo providers. Keep that local database out of GitHub; it is generated automatically.

## The main idea, in plain language

The browser is the customer-facing page. When someone submits a request, its JavaScript sends a request to the Python API. The API checks the input and consent, saves it in SQLite during local development or PostgreSQL in public hosting, then returns a confirmation. Private request data is available only after owner sign-in.

For example, creating a request travels through:

`Request form → JavaScript fetch() → POST /api/requests → input validation → SQLite INSERT → JSON response → updated request list`

## Routes to explore

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/providers` | List providers; add `?category=Gardening` to filter |
| POST | `/api/providers` | Add a provider |
| PUT | `/api/providers/{id}` | Update a provider |
| DELETE | `/api/providers/{id}` | Remove a provider |
| POST | `/api/requests` | Create a customer request |
| GET | `/api/requests` | List requests with their provider names |
| PATCH | `/api/requests/{id}/status` | Change a request status (owner only) |
| DELETE | `/api/requests/{id}` | Delete a request (owner only) |
| GET | `/api/summary` | Return provider/request counts |
| GET | `/api/admin/requests.csv` | Download a private request backup (owner only) |

## Concepts to be ready to explain

- **Client and server:** the browser displays the interface; FastAPI receives requests and returns data.
- **REST API:** routes use HTTP methods to describe actions. GET reads, POST creates, PATCH updates, and DELETE removes.
- **JSON:** the agreed text format used to send structured data between JavaScript and Python.
- **Relational database:** providers and service requests are stored in separate tables. A request's `service_id` points to one provider's `id` (a foreign key).
- **CRUD:** create, read, update, delete. This project supports all four across its API routes.
- **Validation and errors:** Pydantic checks submitted fields; the API returns clear errors for missing records or invalid input.
- **Parameterized SQL:** values use `?` placeholders instead of being pasted into SQL strings, which helps prevent SQL injection.
- **Persistence:** SQLite writes to a file, so information stays after the server stops.

## Scope and CV wording

The website has a single owner login for managing a small pilot; it is not a customer or provider account system. Customer contact details and requests are private to the signed-in owner. Public listings omit phone numbers. It does not include online payments or automatic email/SMS notifications.

## Public website preparation

`render.yaml` is a deployment blueprint for a free Render website in Singapore backed by a free Supabase PostgreSQL database in Mumbai. It is intended for a 30-day, low-traffic real-user pilot. The public app uses the remote database because Render's free web service has temporary local storage.

To launch through Render:

1. Publish this project to its own GitHub repository.
2. Create a free Supabase project in Mumbai. In its database settings, copy the session-mode pooler connection string.
3. Create a free Render web service from the project repository using `render.yaml`. Add the Supabase connection string as the `DATABASE_URL` secret; never add it to GitHub.
4. Set a unique `ADMIN_PASSWORD` with at least 16 characters. Render generates the session secret.
5. Enter the real site operator name and a monitored privacy-contact email. The request retention period is set to 30 days for this trial.
6. Deploy and open the generated public URL. Production mode starts without sample businesses. The owner must add only businesses that agreed to be listed.
7. Sign in and download private request backups regularly. Free Supabase does not make automatic backups.

The free service is public but can sleep after 15 minutes without traffic and take about a minute to wake. Supabase Free has a 500 MB database limit and may pause after one week of inactivity; it does not include automatic backups. Free-tier quotas and availability are not a production uptime guarantee. This setup is for a time-limited pilot, not for a growing marketplace. Check [Render free-plan limits](https://render.com/docs/free) and [Supabase pausing and limits](https://supabase.com/pricing).

This is a deployment starting point, not proof that the site has been launched or legally reviewed. It remains local until a free Supabase database and Render service are created and connected.

Once you can explain the running version, describe it accurately on your CV, for example:

**Local Business Management & Service Platform** — Python, FastAPI, SQLite/PostgreSQL, REST APIs

- Built a local service directory with provider listing management, service requests, and request-status updates.
- Designed related provider and request tables and implemented REST API routes with input validation and database persistence.

Do not list MySQL, customer accounts, or payment handling; they are not part of this website.

