# protonmail-mcp-server (read-only fork)

A [Model Context Protocol](https://modelcontextprotocol.io) server that lets Claude **read and search** email through a locally running [Proton Mail Bridge](https://proton.me/mail/bridge). It cannot send, reply, forward, move, delete, mark as read, or change folders.

This is a modified copy of [mattias242/protonmail-mcp-server](https://github.com/mattias242/protonmail-mcp-server) at commit `4c17603` (17 March 2026), changed on 9 October 2026. See [CHANGES-READONLY.md](CHANGES-READONLY.md) for exactly what changed and why. Licensed GPL-3.0-or-later, like the original.

## What "read-only" means here

- **Six tools, all read-only:** `list_mailboxes`, `get_mailbox_status`, `list_emails`, `get_email`, `get_email_headers`, `search_emails`.
- **No sending code at all.** The SMTP client and the send, reply and forward tools are deleted, not disabled.
- **Mailboxes are opened read-only** (`EXAMINE`, not `SELECT`) and messages are fetched with `BODY.PEEK`, so reading never marks mail as read.
- **A final guard on the connection.** Every line sent to Bridge is checked; anything other than a single `CAPABILITY`, `LOGIN`, `LOGOUT`, `NOOP`, `LIST`, `STATUS`, `EXAMINE`, `SEARCH` or `FETCH` command is refused before it is sent.
- **Only this computer.** The mail host must be `127.0.0.1`, `::1` or `localhost`.

## What it does not protect against

- Claude can still **read** every folder you allow (all of them by default). Use `PROTONMAIL_ALLOWED_MAILBOXES` below to narrow that.
- Whatever Claude reads is sent to Anthropic as part of the conversation, like text you paste in.
- An email can contain text written to manipulate an AI assistant. This server gives such text nothing to act with, but if Claude has *other* tools connected (another mail account, a browser, file access), those are still in play. Keep tool approvals on.
- It has been tested against a simulated mail server, not against a real Proton Mail Bridge.

## Requirements

- [Proton Mail Bridge](https://proton.me/mail/bridge) installed and signed in
- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

## Installation

The read-only version is on the `readonly` branch of this repository. Clone it somewhere permanent, then install:

```bash
git clone -b readonly https://github.com/electromaglabs/protonmail-mcp-readonly
cd protonmail-mcp-readonly
uv sync
```

Use `uv` as shown. It installs the exact dependency versions pinned in `uv.lock`; installing with plain `pip` would pull in version 2 of the MCP SDK, which this code does not support.

## Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "protonmail-readonly": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/protonmail-mcp-readonly", "protonmail-mcp"],
      "env": {
        "PROTONMAIL_USERNAME": "user@proton.me",
        "PROTONMAIL_PASSWORD": "bridge-password",
        "PROTONMAIL_ALLOWED_MAILBOXES": "Labels/Claude"
      }
    }
  }
}
```

`PROTONMAIL_PASSWORD` is the password shown in the Bridge app, not your Proton account password. Remove the `PROTONMAIL_ALLOWED_MAILBOXES` line to allow every folder.

## Limiting Claude to specific emails

Set `PROTONMAIL_ALLOWED_MAILBOXES` to a comma-separated list of folders or labels. Every other mailbox is hidden from `list_mailboxes` and refused by the other tools before anything is sent to Bridge.

A simple way to share only chosen emails: create a label in Proton Mail (for example `Claude`), apply it to the emails you want Claude to see, and set:

```
PROTONMAIL_ALLOWED_MAILBOXES=Labels/Claude
```

Names must match exactly what Bridge reports (labels appear as `Labels/<name>`, custom folders as `Folders/<name>`). Run once without the setting and ask Claude to list mailboxes if you are unsure of a name. Subfolders are not included automatically; list each one.

## Available tools (6)

| Tool | Description |
|------|-------------|
| `list_mailboxes` | List the folders and labels the server may read (with `type: folder\|label`) |
| `get_mailbox_status` | Count messages and unread in a folder |
| `list_emails` | List emails with metadata, newest first, paginated (`page`, `page_size` 1-100) |
| `get_email` | Fetch an email. `body_format`: `text` (default), `stripped`, or `full`; `max_length` limits body text (default 500) |
| `get_email_headers` | Fetch the main headers only, no body |
| `search_emails` | Search one folder by sender, subject, date (`YYYY-MM-DD`) and read/unread |

In `text` and `stripped` mode `get_email` returns plain text only. The raw HTML and the complete header list are returned only when `body_format` is `full`. Attachments are listed by name, type and size; their content is never returned.

## Configuration

All settings use the `PROTONMAIL_` prefix and can be set as environment variables or in a `.env` file in the folder the server is started from:

| Variable | Default | Description |
|----------|---------|-------------|
| `PROTONMAIL_USERNAME` | (required) | Your Proton email address |
| `PROTONMAIL_PASSWORD` | (required) | Bridge-generated password |
| `PROTONMAIL_IMAP_HOST` | `127.0.0.1` | Must be this computer |
| `PROTONMAIL_IMAP_PORT` | `1143` | Bridge IMAP port |
| `PROTONMAIL_ALLOWED_MAILBOXES` | (all) | Comma-separated folders/labels Claude may read |

The original server's `PROTONMAIL_SMTP_*` and `PROTONMAIL_VERIFY_SSL` settings no longer exist and are ignored if present.

## Testing

```bash
# Unit and BDD tests (no Bridge required)
uv run pytest tests/unit/ tests/features/ -v

# Integration tests (requires running Bridge + .env); these only read
uv run pytest tests/integration/ -m integration -v
```

## Technical notes

- Proton Mail Bridge v3 exposes IMAP on `127.0.0.1:1143` as plain TCP. The connection is persistent (one per server session) with automatic reconnect.
- `aiosmtplib` is still listed in `pyproject.toml` and `uv.lock` so that the lockfile stays identical to the reviewed original. Nothing imports it.

## License

GNU General Public License v3.0 or later. See [LICENSE](LICENSE). Original work by Mattias Wahlberg.
