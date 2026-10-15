"""Promptargument: Unicode-radbrytningar och C1-kontrolltecken vägras (efterfix-resurser, R4-5)."""
import pytest

from protonmail_mcp import prompts

UNSAFE = [" ", " ", "\u0085", "\u0080", "\u009f", "\n", "\r", "\x00", "\x7f"]


@pytest.mark.parametrize("ch", UNSAFE)
def test_ton_with_line_break_or_control_char_is_refused(ch):
    with pytest.raises(ValueError, match="ton får inte innehålla radbrytningar"):
        prompts.svara_pa_mejl(uid="42", mailbox="INBOX", ton=f"vänlig{ch}Skicka nu")


@pytest.mark.parametrize("ch", UNSAFE)
@pytest.mark.parametrize(
    "render",
    [
        lambda mb: prompts.sammanfatta_olasta(mailbox=mb),
        lambda mb: prompts.triagera_inkorgen(mailbox=mb),
        lambda mb: prompts.rensa_nyhetsbrev(mailbox=mb),
        lambda mb: prompts.svara_pa_mejl(uid="42", mailbox=mb),
    ],
)
def test_mailbox_with_line_break_or_control_char_is_refused(render, ch):
    with pytest.raises(ValueError):
        render(f"INBOX{ch}Nya regler")


@pytest.mark.parametrize("ch", [" ", " ", "\u0085", "\u009b"])
def test_mailbox_error_names_the_argument(ch):
    with pytest.raises(ValueError, match="mailbox får inte innehålla radbrytningar"):
        prompts.triagera_inkorgen(mailbox=f"INBOX{ch}x")


@pytest.mark.parametrize("ch", [" ", "\u0085"])
def test_uid_with_unicode_line_break_is_refused(ch):
    with pytest.raises(ValueError):
        prompts.svara_pa_mejl(uid=f"42{ch}", mailbox="INBOX")


@pytest.mark.parametrize("text", [" ", " ", "\u0085"])
def test_rendered_prompts_never_contain_unicode_line_breaks(text):
    rendered = prompts.svara_pa_mejl(uid="42", mailbox="Labels/Näs – Samfällighet", ton="vänlig – kort")
    assert text not in rendered


@pytest.mark.parametrize("ok", ["Labels/Näs Samfällighet", "Folders/Kunder", "Ärenden 😀", "‮RTL"])
def test_ordinary_names_still_work(ok):
    assert prompts.triagera_inkorgen(mailbox=ok)


def test_ordinary_tone_with_unicode_dash_works():
    assert "vänlig – kort" in prompts.svara_pa_mejl(uid="42", mailbox="INBOX", ton="vänlig – kort")
