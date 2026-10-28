# Barak Valley Connect

A public pilot website for discovering local service providers in Silchar, Assam.

**Live website:** https://barak-valley-connect.onrender.com

## What visitors can do

- Browse providers by service category and area.
- Send a service request with their contact details and consent to follow-up.
- Read the privacy notice.

## What the website owner can do

- Sign in to add, edit, and remove business listings.
- Review service requests and update their status.
- Download a private CSV backup of requests.

Provider phone numbers are visible only to the signed-in owner. Public visitors use the request form. Add a business only after its owner agrees to be listed.

## Built with

- **Backend:** Python, FastAPI, REST API
- **Frontend:** HTML, CSS, vanilla JavaScript
- **Database:** SQLite for local development; Supabase PostgreSQL for the hosted website
- **Hosting:** Render

## Run locally on macOS

1. Install Python 3.
2. Open Terminal in the project folder.
3. Create and activate a virtual environment:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install the dependencies:

   ```sh
   python -m pip install -r requirements.txt
   ```

5. Copy `.env.example` to `.env`. Set your own local `ADMIN_PASSWORD` and `SESSION_SECRET`.
6. Start the site:

   ```sh
   python -m uvicorn main:app --reload
   ```

7. Open http://127.0.0.1:8000. The local development database starts with sample providers; the live website starts empty.
8. Stop the server with Control+C.

Never upload `.env`, database files, or real passwords to GitHub.

## How it works

The page uses JavaScript to send requests to the FastAPI backend. FastAPI validates the submitted data and stores it in a database. Local development uses SQLite; the live service uses Supabase PostgreSQL. A customer request is linked to a provider by its database ID.

## Project concepts

- **REST API:** HTTP routes let the browser read, add, edit, and remove data.
- **CRUD:** create, read, update, and delete operations for provider listings and service requests.
- **Relational database:** provider and request records are stored in related tables.
- **Validation:** Pydantic checks data before it is saved.
- **Parameterized SQL:** database values are passed separately from SQL commands.
- **Sessions:** the owner sign-in is maintained with a protected session cookie.

## Current scope

This is an early pilot with one owner login. It does not have provider or customer accounts, online payments, or automatic email/SMS alerts. The owner checks requests manually. Free hosting may sleep when idle, and free database services have usage limits; this setup is suitable for a small pilot rather than a high-traffic production service.

## CV summary

**Barak Valley Connect** — Python, FastAPI, JavaScript, SQLite/PostgreSQL

- Built a local service directory with category filtering, owner-managed provider listings, and customer service requests.
- Implemented REST API routes, input validation, session-based owner access, and persistent database storage.
