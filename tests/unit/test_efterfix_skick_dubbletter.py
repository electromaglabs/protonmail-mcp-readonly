"""RCPT TO dedupliceras utan hänsyn till skiftläge i alla skickvägar, och
mottagarlistans längd har ett hårt tak (granskning 3, policy F2)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from protonmail_mcp import smtp_client
from protonmail_mcp.smtp_client import SMTPClient
from tests.llm_skick_support import BridgeSpy, make_settings, record_smtp


async def _send(settings, **kwargs):
    spy = BridgeSpy()
    smtp = SMTPClient(settings)
    with record_smtp(spy) as captured:
        await smtp.send_email(subject="Hej", body="Hej", **kwargs)
    return captured, spy


async def test_send_email_dedupes_rcpt_case_insensitively():
    captured, _ = await _send(
        make_settings(max_recipients=1),
        to=["victim@x.se"] * 3 + ["Victim@x.se", "VICTIM@X.SE", "vIcTiM@x.se"],
    )
    assert captured.recipients == ["victim@x.se"]


async def test_dedupe_keeps_first_occurrence_across_fields():
    captured, _ = await _send(
        make_settings(), to="Anna@Exempel.se", cc=["bo@exempel.se"], bcc=["anna@exempel.se", "BO@exempel.se"]
    )
    assert captured.recipients == ["Anna@Exempel.se", "bo@exempel.se"]


async def test_idn_variants_are_the_same_recipient():
    captured, _ = await _send(make_settings(), to=["x@exämple.se", "x@xn--exmple-cua.se", "X@EXÄMPLE.SE"])
    assert captured.recipients == ["x@xn--exmple-cua.se"]


async def test_audit_records_deduplicated_recipients(monkeypatch):
    seen = {}

    def record(settings, action, **fields):
        seen.update(fields)

    monkeypatch.setattr(smtp_client.audit, "record", record)
    await _send(make_settings(), to=["a@x.se", "A@x.se"])
    assert seen["recipients"] == ["a@x.se"]


async def test_hard_cap_on_list_length_before_validation(monkeypatch):
    calls = []
    real = smtp_client._validate_email_addr
    monkeypatch.setattr(smtp_client, "_validate_email_addr", lambda a: calls.append(a) or real(a))
    spy = BridgeSpy()
    smtp = SMTPClient(make_settings(max_recipients=0))
    with record_smtp(spy), pytest.raises(ValueError, match="för många adresser"):
        await smtp.send_email(to=["a@x.se"] * (smtp_client.MAX_RECIPIENT_ENTRIES + 1), subject="Hej", body="Hej")
    assert calls == []  # vägrat innan någon adress bearbetades
    assert not spy.contacted


async def test_hard_cap_counts_all_fields_together():
    n = smtp_client.MAX_RECIPIENT_ENTRIES // 2 + 1
    smtp = SMTPClient(make_settings(max_recipients=0))
    with pytest.raises(ValueError, match="för många adresser"):
        await smtp.send_email(to=["a@x.se"] * n, bcc=["b@x.se"] * n, subject="Hej", body="Hej")


async def test_list_at_cap_is_accepted_when_deduplicated():
    captured, _ = await _send(
        make_settings(max_recipients=1), to=["a@x.se"] * smtp_client.MAX_RECIPIENT_ENTRIES
    )
    assert captured.recipients == ["a@x.se"]


def test_draft_builder_has_the_same_hard_cap():
    from protonmail_mcp.tools.drafts import _build_draft

    app = SimpleNamespace(smtp=SimpleNamespace(account_address="me@proton.me"))
    with pytest.raises(ValueError, match="för många adresser"):
        _build_draft(app, to=["a@x.se"] * (smtp_client.MAX_RECIPIENT_ENTRIES + 1), subject="Hej", body="Hej")


async def test_reply_path_dedupes_too():
    """reply_to_email och forward_email går genom send_email och får samma deduplicering."""
    smtp = SMTPClient(make_settings())
    smtp._deliver = AsyncMock(return_value=True)
    await smtp.send_email(to="a@x.se", cc=["A@X.se", "b@x.se"], subject="Re: Hej", body="Tack")
    assert smtp._deliver.await_args.args[1] == ["a@x.se", "b@x.se"]
