"""Enhetstester: mailbox obligatorisk i get_email/get_email_headers (llm-kontrakt, K4/K5)."""
import inspect

import pytest

from protonmail_mcp.tools.messages import get_email, get_email_headers, list_emails
from protonmail_mcp.tools.search import search_emails


@pytest.mark.parametrize("tool", [get_email, get_email_headers], ids=lambda t: t.__name__)
def test_mailbox_has_no_default(tool):
    assert inspect.signature(tool).parameters["mailbox"].default is inspect.Parameter.empty


@pytest.mark.parametrize("tool", [get_email, get_email_headers], ids=lambda t: t.__name__)
def test_docstring_explains_why(tool):
    doc = inspect.getdoc(tool)
    assert "standard: INBOX" not in doc
    assert "obligatorisk" in doc and "UID:n gäller per mapp" in doc


@pytest.mark.parametrize("tool", [list_emails, search_emails], ids=lambda t: t.__name__)
def test_listing_tools_keep_inbox_default(tool):
    # De tar inget UID; INBOX är en rimlig startpunkt
    assert inspect.signature(tool).parameters["mailbox"].default == "INBOX"


def test_headers_docstring_documents_raw_values_and_missing_keys():
    doc = inspect.getdoc(get_email_headers)
    assert "RFC 2047" in doc and "avkodas inte" in doc
    assert "saknas" in doc
    assert "to och cc" in doc  # råa strängar här, listor i get_email
