# Domain Context

## Purpose

Personal Telegram keeps one searchable registry of Telegram groups, channels,
and bots while allowing several Telegram user accounts to discover and manage
the records they can access.

## Domain Terms

### Telegram Account

An authenticated Telegram user identity. Each Telegram Account has its own
authorization lifecycle and must never share an authorization session with
another Telegram Account.

### Registry Bot

The canonical local record for one Telegram bot. A Registry Bot may be known
through one or more Telegram Accounts and may exist before its token is known.

### Account Ownership

The relationship recording that a Telegram Account currently owns a Registry
Bot according to Telegram.

### Account Access

The relationship recording that a Telegram Account can see a channel or group.

### Tokenless Bot

A Registry Bot discovered through Telegram ownership whose token is not yet in
the local registry. It remains editable so a token can be supplied later.

### Account Flag

A user-selected country marker for a Telegram Account. It is presentation
metadata and does not determine the account's phone number or authorization.

## Invariants

- A Telegram Account has exactly one isolated server-side authorization
  session.
- A Telegram bot has at most one canonical Registry Bot record.
- A channel or group has at most one canonical local record.
- Account Ownership and Account Access may associate a canonical record with
  several Telegram Accounts.
- Discovering a bot never overwrites a known token with an empty token.
- Removing or losing an account association does not delete the canonical bot,
  channel, group, tags, or notes.
- Phone numbers, verification codes, passwords, session paths, and full bot
  tokens are not returned by registry APIs.

## Key Workflows

### Authorize an account

Create or select a Telegram Account, request a verification code, submit the
code and optional two-step verification password, then persist the authorized
session for that Telegram Account.

### Scan owned bots

For a selected authorized Telegram Account, request the bots it owns from
Telegram, match them to canonical Registry Bots, create Tokenless Bots when
needed, and refresh Account Ownership relationships.

### Ingest channels and groups

For a selected authorized Telegram Account, fetch its dialogs, update canonical
channel and group records, and refresh Account Access relationships.
