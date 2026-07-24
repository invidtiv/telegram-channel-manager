# ADR 0001: Model Telegram accounts through associations

- Status: Accepted
- Date: 2026-07-24

## Context

The application must support several independently authenticated Telegram
accounts. The same bot, channel, or group can appear in more than one account,
while local tags, notes, projects, and tokens must remain consistent.

## Decision

Keep bots, channels, and groups as canonical records. Store Telegram Accounts
separately and connect them through Account Ownership and Account Access
relationships. Store one isolated server-side Telegram session per account.

## Consequences

- Shared records show several account flags without duplicated local metadata.
- Scanning one account can refresh its associations without deleting records
  used by another account.
- Queries must explicitly filter through account associations.
- Existing single-account data needs a default-account migration.

## Alternatives considered

- Duplicate every bot and group per account. Rejected because tokens, tags, and
  notes would drift and shared records would be hard to identify.
- Keep one session and switch credentials in place. Rejected because it risks
  cross-account authorization state and cannot safely support concurrent use.
