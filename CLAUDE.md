# protonmail-mcp (read-only fork)

MCP server that exposes Proton Mail Bridge (IMAP on localhost) as **read-only** MCP tools. See README.md and CHANGES-READONLY.md.

## Invariants: do not weaken these

- No write tools and no SMTP code. Do not add tools that send, move, delete, flag or create anything.
- Mailboxes are opened with `EXAMINE`; bodies and headers are fetched with `BODY.PEEK[...]`.
- Every string that reaches the IMAP connection is validated first (`_validate_uid`, `_mailbox`, `_to_imap_date`, `_search_string`), using `fullmatch`, never `match(...$)`.
- `_check_outgoing_line` / `_ALLOWED_COMMANDS` in `imap_client.py` is the last line of defence. Do not add write commands to the allow-list.
- Never log setting values or raw IMAP command lines (the LOGIN line contains the password).

## Run locally

```bash
uv sync
cp .env.example .env   # fill in username + Bridge password
uv run protonmail-mcp  # stdio transport
```

## Structure

```
src/protonmail_mcp/
├── server.py        # FastMCP + lifespan (lazy IMAP connection)
├── config.py        # pydantic-settings, prefix PROTONMAIL_, loopback-only host, mailbox allow-list
├── imap_client.py   # persistent read-only IMAP client + outgoing command guard
├── email_parser.py  # RFC822 -> dict, body_format, max_length
└── tools/           # 6 read-only MCP tools
    ├── mailboxes.py # list_mailboxes, get_mailbox_status
    ├── messages.py  # list_emails, get_email, get_email_headers
    └── search.py    # search_emails
```

## Tests

```bash
uv run pytest tests/unit/ tests/features/        # fast, no Bridge needed
uv run pytest tests/integration/ -m integration  # needs a running Bridge and .env; read-only
```

## Notes

- Bridge v3 IMAP is plain TCP on 127.0.0.1:1143. `IMAP4_SSL` against that port fails.
- `aioimaplib` 2.0.1 does not track `EXAMINE` as an open mailbox, so `_open_readonly` sets the protocol state itself.
- `aioimaplib` 2.0.1 does not support `uid("search")`; use `search()` then `fetch()`.
- The code targets MCP SDK 1.x (`mcp.server.fastmcp`). Keep using `uv.lock`.
