# Public website launch checklist

## What is ready

- Browser website for finding services and submitting a request.
- Owner-only sign-in for managing listings and viewing requests.
- Public visitors do not receive customer names, phone numbers, request details, or business phone numbers from the API.
- Request form requires agreement to the privacy notice and limits repeated submissions from one connection.
- Production mode does not insert the fictional development sample businesses.
- Deployment blueprint uses a free Render service, a Supabase PostgreSQL database, and a health check.

## What must be decided or supplied before launch

1. **Website owner details:** the real owner/operator name and a monitored email address for the privacy notice.
2. **Privacy choices:** how long to keep requests, and how people can ask to see or delete their information. The current privacy page is a draft with placeholders.
3. **Listings:** add only real businesses whose owners agreed to have their business information published. The live database starts empty.
4. **Follow-up:** decide who checks requests. The website currently stores requests for the owner to check; it does not email or text notifications.
5. **Hosting location:** the prepared Render service runs in Singapore and the Supabase database should be created in Mumbai. Render currently doesn't offer India as a web-service region. See [Render regions](https://render.com/docs/regions) and [Supabase regions](https://supabase.com/docs/guides/platform/regions).
6. **Hosting accounts:** both providers have a $0 tier for this pilot, within their quotas. Render can sleep after 15 idle minutes; Supabase can pause an inactive free database after a week. Supabase Free does not include automatic backups. See [Render free limits](https://render.com/docs/free) and [Supabase free-plan pausing](https://supabase.com/docs/guides/platform/free-project-pausing).
7. **Public project repository:** publish the source code to a new GitHub repository. The local database and `.env` secrets are excluded; never upload either one.
8. **Address:** the host can supply a public `onrender.com` website address. A custom domain is optional and would need to be purchased separately.

## Launch sequence

1. Publish this project to its own GitHub repository.
2. Create a free Supabase project in Mumbai and copy its session pooler connection string into Render's secret field.
3. Set a unique owner password of at least 16 characters in the hosting dashboard. Render generates the session secret.
4. Enter the actual operator name and privacy email, and keep the 30-day request retention setting.
5. Complete the privacy notice and add only listings whose owners agreed to publication.
6. Create the free Render service and make sure no paid plan or add-on is selected.
7. Sign in to the live website, add approved businesses, submit a test request, confirm it is private to the owner, and delete the test request.
8. Download private request backups regularly and share the website address after the live browser check succeeds.

## Current pilot limits

- One website owner manages listings; businesses cannot create their own logins yet.
- The website owner follows up manually; there are no automatic email or text alerts.
- There is no payment processing or customer account system.
- The free Render website sleeps after idle time and the Supabase free database may pause after inactivity. The site can be slow to wake and free tiers do not guarantee production uptime.
- Supabase Free has no automatic backups. Download the private CSV backup regularly; if activity becomes valuable, upgrade database, hosting, and backups before inviting more users.
- Do not use the local sample entries or local customer records as live data.

