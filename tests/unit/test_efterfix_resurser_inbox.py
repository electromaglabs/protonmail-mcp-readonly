"""canonical_uri: INBOX utan hänsyn till skiftläge, som imap_idle.mailbox_key (efterfix-resurser, R4-1)."""
import pytest

from protonmail_mcp import resources, subscriptions
from protonmail_mcp.imap_idle import mailbox_key


@pytest.mark.parametrize("spelling", ["inbox", "Inbox", "INBOX", "iNbOx"])
def test_mailbox_uri_for_inbox_is_canonical_uppercase(spelling):
    assert resources.canonical_uri(f"mailbox://{spelling}") == "mailbox://INBOX"


@pytest.mark.parametrize("spelling", ["inbox", "Inbox", "INBOX"])
def test_email_uri_for_inbox_is_canonical_uppercase(spelling):
    assert resources.canonical_uri(f"email://{spelling}/42") == "email://INBOX/42"


@pytest.mark.parametrize("name", ["Archive", "archive", "Folders/inbox", "INBOX/Sub", "inbox2"])
def test_other_names_are_kept_exactly(name):
    assert resources.canonical_uri(resources.mailbox_uri(name)) == resources.mailbox_uri(name)
    assert resources.canonical_uri(resources.email_uri(name, 7)) == resources.email_uri(name, 7)


@pytest.mark.parametrize("name", ["inbox", "Inbox", "Archive", "Folders/A/B", "Näs"])
def test_same_rule_as_the_watcher(name):
    assert resources.canonical_uri(resources.mailbox_uri(name)) == resources.mailbox_uri(mailbox_key(name))


def test_subscription_with_lowercase_inbox_matches_watcher_uri():
    registry = subscriptions.SubscriptionRegistry()
    session = object()
    registry.subscribe(session, "mailbox://inbox")
    assert registry.subscribers(resources.mailbox_uri("INBOX")) == [(session, "mailbox://inbox")]
