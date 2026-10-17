# Changes in the read-only fork

Based on [mattias242/protonmail-mcp-server](https://github.com/mattias242/protonmail-mcp-server) at commit `4c17603e27b1f947b2a045d4e6ffba34c12ea2d1` (17 March 2026). Modified 9 October 2026. `pyproject.toml`, `uv.lock` and `LICENSE` are unchanged.

## Removed

- **All write tools:** `send_email`, `reply_to_email`, `forward_email`, `move_email`, `delete_email`, `mark_email_read`, `mark_email_unread`, `create_folder`, `delete_folder`, `rename_folder`.
- **`smtp_client.py`** and every SMTP setting. The server has no code path that can send mail.
- **The write methods of `IMAPClient`:** `set_flags`, `move_message`, `delete_message`, `create_folder`, `delete_folder`, `rename_folder`.
- The tests that covered the removed features.

Six read tools remain: `list_mailboxes`, `get_mailbox_status`, `list_emails`, `get_email`, `get_email_headers`, `search_emails`. Each is annotated `readOnlyHint: true`.

## Fixed

1. **IMAP command injection in `search_emails`.** `since` and `before` were passed through unchecked when they were not `YYYY-MM-DD`, and `subject` and `from_addr` escaped quotes but not line breaks. A value containing a line break was sent to Bridge as a second command (for example a folder `DELETE`). Dates are now parsed and rebuilt from numbers; text filters reject every control character and are capped at 200 characters. All validation happens before anything is sent.
2. **Validation accepted a trailing line break.** The UID and mailbox checks used `re.match(... $)`, and `$` also matches just before a final newline, so `"INBOX\n"` passed. They now use `fullmatch`.
3. **Reading marked mail as read.** `get_email` used `BODY[]` and `list_emails` used `BODY[HEADER.FIELDS ...]`; both now use `BODY.PEEK[...]`. Mailboxes are also opened with `EXAMINE` (read-only) instead of `SELECT`.
4. **A failed mailbox open fell through to the next command.** If a mailbox could not be opened, the original still issued the fetch. The fork raises an error instead.
5. **Folder names with spaces.** Mailbox names were sent unquoted, so `Folders/My Stuff` was split into two arguments. Names are now sent as IMAP quoted strings.
6. **Password in the log.** If `PROTONMAIL_USERNAME` was missing, the startup error (and its traceback) printed the supplied settings, including the Bridge password. The error now lists field names and messages only. The login line no longer logs the email address either.
7. **`get_email` returned more than `max_length` suggests.** The limit applied only to the plain-text body while the full HTML body and every header were always returned. In `text` and `stripped` mode the raw HTML and header dump are now omitted; `full` still returns everything. The HTML-to-text fallback now drops scripts, style sheets and comments and decodes entities.
8. **A made-up charset in a header crashed the tool call.** Header decoding now falls back to UTF-8.
9. **`list_emails` paging.** A page past the end returned the oldest message; it now returns an empty page. `page` must be 1 or more and `page_size` 1-100.
10. **`python -m protonmail_mcp.server` started a server with no tools.** It now runs the same entry point as the `protonmail-mcp` command.

## Added

- **Outgoing command guard** (`_check_outgoing_line` in `imap_client.py`). Every line handed to the IMAP connection must be a single line and one of `CAPABILITY`, `LOGIN`, `LOGOUT`, `NOOP`, `LIST`, `STATUS`, `EXAMINE`, `SEARCH`, `FETCH`. Anything else raises before it is written to the socket. The server refuses to start if the guard cannot be installed.
- **Local host only.** `PROTONMAIL_IMAP_HOST` must be `127.0.0.1`, `::1` or `localhost`, because the IMAP connection to Bridge is unencrypted.
- **`PROTONMAIL_ALLOWED_MAILBOXES`** (optional). A comma-separated allow-list of folders and labels. Other mailboxes are hidden from `list_mailboxes` and refused by every other tool before any command is sent.
- Tests for each item above (`tests/unit/`), including checks that the tool list is exactly the six read tools and that no write module can be imported.

## Not changed, and still true

- Email content is untrusted text. Hidden text in an HTML email still reaches the model; this fork only ensures the server has nothing to act with.
- Dependencies are the original's pinned versions from March 2026. `aiosmtplib` remains in the lockfile but is not imported.
- Verified against a simulated IMAP server, not a real Proton Mail Bridge.
