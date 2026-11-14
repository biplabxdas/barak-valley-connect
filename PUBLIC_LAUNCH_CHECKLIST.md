# Barak Valley Connect — live pilot notes

**Live website:** https://barak-valley-connect.onrender.com  
**GitHub source:** https://github.com/biplabxdas/barak-valley-connect

## Current status

The existing website is documented at the Render URL above. The account, provider profile, and matching changes are on `codex/final-barak-valley-connect` and in draft PR #2; they have not been merged or deployed, and the current live URL was not checked as part of this local verification.

New production installations start with an empty directory. Customer and provider registrations create accounts; provider registration creates a public listing. Confirm provider consent and business details before promoting the updated site.

## Before inviting a business

- Confirm the business owner agrees to the listing and public display of its business name, category, and service area.
- Provider phone numbers are visible to the signed-in website owner and the provider who owns that listing; they are not public.
- The owner can review every request. A provider can review requests for their own listing, and a signed-in customer can review their own request status.
- There are no automatic email or text alerts. Provider emails are not verified, and password recovery is not implemented.
- Test a service request using non-sensitive sample details, confirm it appears in the owner area, then delete the test request.
- Download private request backups regularly; the current app does not create database backups automatically.
- Do not commit `.env`, database files, connection strings, passwords, or customer request data to GitHub.

## Current pilot limits

- One owner credential configured through private environment settings, plus customer and provider accounts.
- Provider registrations publish a listing immediately; there is no approval or email-verification queue.
- No payment processing.
- Render's free web service may sleep when idle; availability and persistence depend on the selected PostgreSQL plan.
- Free hosting is suitable for a small pilot, not a production uptime guarantee.

## Hosting

- Render web service: free plan, Singapore region.
- Render PostgreSQL: declared as a same-region Blueprint resource. `render.yaml` does not pin a database plan, so review the plan and any cost shown by Render before syncing the Blueprint.
- The database connection string and owner credentials belong in Render's private environment settings, never in this repository.

See the [Render free-plan limits](https://render.com/docs/free) and [Render PostgreSQL pricing and plans](https://render.com/docs/postgresql).
