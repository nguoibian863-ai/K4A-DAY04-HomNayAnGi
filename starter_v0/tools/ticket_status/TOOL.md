---
name: ticket_status
track: bonus
kind: local_read
provider: mock_ticket_store
requires_env: []
inputs: [ticket_id]
outputs: [ticket_id, summary, priority, asset_id, created_at, source]
side_effect: false
---
# ticket_status

Looks up one previously created support ticket by its `ticket_id` (the ID
returned by `create_ticket`, shape `LAB-XXXXXXXX`). Read-only: it never
creates, edits, or deletes ticket files, and it never fabricates a ticket
that does not exist.

Use this to answer "what's the status of my ticket / did that ticket get
created" follow-up questions, instead of calling `create_ticket` again.

Guardrails:

- `ticket_id` must match the exact ID shape `create_ticket` generates
  (`LAB-` + 8 hex characters). Anything else — including path-like input
  such as `../../.env` — is rejected before touching the filesystem, so this
  tool cannot be used to read arbitrary files.
- Returns `ticket_not_found` for a well-formed but unknown ID, instead of
  guessing or inventing ticket data.
- Ticket payloads themselves never contain credentials, tokens, or other
  sensitive fields — `create_ticket` already rejects those at creation time.
