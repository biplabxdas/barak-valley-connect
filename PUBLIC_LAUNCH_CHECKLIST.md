# Barak Valley Connect — live pilot notes

**Live website:** https://barak-valley-connect.onrender.com  
**GitHub source:** https://github.com/biplabxdas/neighbourhood-local-services

## Current status

The website is deployed on Render and uses a Supabase PostgreSQL database. Production starts with an empty provider directory. The owner signs in and adds only businesses that have agreed to be listed.

## Before inviting a business

- Confirm the business owner agrees to the listing and public display of its business name, category, and service area.
- Provider phone numbers are visible only to the signed-in website owner; visitors contact providers by sending a request through the site.
- The site owner must check requests manually. There are no automatic email or text alerts.
- Test a service request using non-sensitive sample details, confirm it appears in the owner area, then delete the test request.
- Download private request backups regularly. Supabase Free does not include automatic backups.
- Do not commit `.env`, database files, connection strings, passwords, or customer request data to GitHub.

## Current pilot limits

- One owner login; businesses and customers do not have accounts.
- No payment processing.
- Render's free web service may sleep when idle; Supabase Free has quotas and can pause an inactive project.
- Free hosting is suitable for a small pilot, not a production uptime guarantee.

## Hosting

- Render web service: free plan, Singapore region.
- Supabase PostgreSQL: free project, Mumbai region.
- The database connection string and owner credentials belong in Render's private environment settings, never in this repository.

See the [Render free-plan limits](https://render.com/docs/free) and [Supabase free-plan limits](https://supabase.com/docs/guides/platform/free-project-pausing).
