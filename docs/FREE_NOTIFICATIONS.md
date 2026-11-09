# Free ntfy push notifications

The existing outbox worker supports `NTFY_TOPIC` as an alternative to
`OUTBOX_WEBHOOK_URL`. Configure only one. Use a random 32–128 character topic,
for example from `openssl rand -hex 24`, and keep it in the worker's protected
environment. Subscribe at `https://ntfy.sh/<your-topic>` in a browser or app.

Only the project label and event UUID leave the service. Approval payloads,
workspace data, request text and credentials are not forwarded. The durable
outbox retains its lease/retry/dead-letter behavior. Redirects are rejected.
ntfy does not promise deduplication: a lost acknowledgement can cause a repeat.

Anonymous ntfy.sh currently permits 250 messages per visitor/day at no charge.
Free topics are unlisted public channels, not authenticated private storage.
Treat the random topic as a subscription secret. Quotas and availability can
delay delivery; inspect the outbox and the owner workspace too. The adapter
does not create a deployed worker, users or tokens automatically.

Provider documentation: https://docs.ntfy.sh/publish/ and https://docs.ntfy.sh/privacy/.

The free scheduled workflow requires `CONTENT_APPROVAL_DATABASE_URL` and exactly
one destination: `CONTENT_APPROVAL_NTFY_TOPIC` or
`CONTENT_APPROVAL_OUTBOX_WEBHOOK_URL` (with its optional
`CONTENT_APPROVAL_OUTBOX_WEBHOOK_TOKEN`). It validates these before installing
dependencies or claiming events. Missing secrets cannot silently use a local
SQLite database or mark a temporary runner file as an external delivery.
Migrations belong to the deployment step, not the recurring delivery job.
Retries, rejected delivery and lost leases make the one-shot run fail while
retaining the event in the durable queue. Runs do not overlap.
GitHub schedules can be delayed and public-repository schedules are disabled
after 60 days without repository activity; this is not a five-minute delivery SLA.
Adding this workflow does not configure repository secrets or prove live delivery.
