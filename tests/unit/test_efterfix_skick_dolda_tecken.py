"""Mottagaradresser med dolda tecken (Cf, taggtecken, bidi, nollbredd …)
vägras i _validate_email_addr, som alla skick- och utkastvägar går igenom
(granskning 3, injektion F6)."""
from email.message import EmailMessage

import pytest

from protonmail_mcp.smtp_client import _validate_email_addr, prepared_recipients

HIDDEN = [
    "boss\U000E0041\U000E0042@company.com",  # taggtecken
    "b‮oss@company.com",  # RLO
    "boss⁦@company.com",  # LRI
    "boss​@company.com",  # nollbreddsmellanslag
    "boss‌@company.com",  # ZWNJ
    "boss‍@company.com",  # ZWJ
    "boss­@company.com",  # mjukt bindestreck
    "boss⁠@company.com",  # WORD JOINER
    "boss﻿@company.com",  # BOM
    "boss‎@company.com",  # LRM
    "boss@compa​ny.com",  # i domänen
    "boss️@company.com",  # variationsväljare
    "boss\x7f@company.com",  # kontrolltecken
    "bossㅤ@company.com",  # hangul-fyllnad (ritas som tomrum)
    "Boss <boss\U000E0041@company.com>",  # med visningsnamn
]


@pytest.mark.parametrize("addr", HIDDEN)
def test_hidden_characters_are_refused(addr):
    with pytest.raises(ValueError, match="dolda tecken"):
        _validate_email_addr(addr)


def test_error_shows_the_hidden_characters_escaped():
    with pytest.raises(ValueError) as exc:
        _validate_email_addr("boss\U000E0041@company.com")
    assert "\\U000e0041" in str(exc.value)
    assert "\U000E0041" not in str(exc.value)


@pytest.mark.parametrize(
    "addr",
    ["anna@exempel.se", "Åsa Öberg <asa@exämple.se>", "user@straße.de", "\"a,b\"@x.se",
     "Familjen 👨‍👩‍👧 <f@x.se>"],
)
def test_visible_addresses_still_pass(addr):
    assert _validate_email_addr(addr) == addr


def test_prepared_recipients_refuses_hidden_bcc():
    msg = EmailMessage()
    msg["To"] = "anna@exempel.se"
    msg.set_content("x")
    msg._headers.append(("Bcc", "spion​@ond.example"))
    with pytest.raises(ValueError, match="dolda tecken"):
        prepared_recipients(msg)


@pytest.mark.parametrize(
    "addr",
    ["boss[U+E0041]@company.com", "boss[u+200b]@company.com", "Boss <b[U+202E]oss@company.com>",
     "boss@company[U+200B].com"],
)
def test_visible_escape_of_hidden_character_is_refused_clearly(addr):
    with pytest.raises(ValueError, match=r"dolda tecken.*\[U\+|\[U\+.*dolda tecken") as exc:
        _validate_email_addr(addr)
    assert "get_email" in str(exc.value)
