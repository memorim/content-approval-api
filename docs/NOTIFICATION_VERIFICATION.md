# Outbox delivery verification — 2026-11-09

GitHub Actions secrets `CONTENT_APPROVAL_DATABASE_URL` and
`CONTENT_APPROVAL_NTFY_TOPIC` are configured. Values are intentionally excluded.
The connection uses the installed psycopg 3 driver (`postgresql+psycopg://`).
The destination is the owner's existing Pulsewatch subscription; the notification
title is Content Approval.

Run: https://github.com/memorim/content-approval-api/actions/runs/42627964632

The workflow completed successfully. Synthetic event
`95712632-08b2-47bb-b2c0-0735ca35d8a8` was published at
2026-11-09T13:43:47.321Z, with one attempt and no last error.
Its workspace and event type explicitly identify technical delivery verification.
No approval request, user credential, or personal data was created for this test.

This verifies an existing outbox event through the GitHub worker and ntfy acceptance;
it does not test API request creation or prove receipt on the owner's device.
Only the event UUID and project title are sent to ntfy, never the event payload.
The deployed API was not redeployed as part of this check.

The workflow now runs every 15 minutes to leave an idle interval for Neon Free's
five-minute scale-to-zero timeout. GitHub schedules can be delayed. Other API
traffic can keep the database awake. No paid background worker was provisioned.
Live verification above used manual dispatch before the cadence change; the new
cadence has not yet been observed firing.

Reference: https://neon.com/docs/introduction/scale-to-zero
