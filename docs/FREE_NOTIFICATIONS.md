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
