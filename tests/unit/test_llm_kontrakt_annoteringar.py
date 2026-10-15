"""Enhetstester: varje verktyg är klassat enligt en explicit tabell (llm-kontrakt).

Tabellen är facit. Ett nytt verktyg som inte står här får testet att falla,
så att den som lägger till det måste ta ställning till hur det klassas.

Kolumner: (readOnlyHint, destructiveHint, idempotentHint, openWorldHint)
- Läsverktyg: läs-endast, inte destruktiva, idempotenta, sluten värld.
  check_new_emails och wait_for_new_email ändrar inget i brevlådan (BODY.PEEK);
  de flyttar bara serverns eget vattenmärke för "sedan förra anropet".
- get_attachment ändrar inget i brevlådan men skriver (med save=True) en ny
  fil i bilagekatalogen. Den skriver aldrig över något (namnkrock ger
  "namn (1)"), alltså inte destruktiv, men inte heller läs-endast eller
  idempotent.
- Markeringar (läst/oläst, stjärna, lägg till etikett) är idempotenta: samma
  anrop igen ändrar inget mer.
- Destruktiva: det som raderar, flyttar, ersätter eller tar bort (etiketter,
  mappar, namn, utkast). remove_label är idempotent (andra gången finns
  etiketten inte, inget mer ändras); move/delete märks inte som idempotenta
  eftersom en upprepning inte är en ofarlig no-op att lita på.
- Skick (send_email, reply_to_email, forward_email, send_draft) når omvärlden
  och kan inte ångras: öppen värld och destruktiva. send_draft tar dessutom
  bort utkastet.
- Utkast som skapas läggs till i Drafts; inget skickas eller skrivs över.
"""
import inspect

import pytest

from protonmail_mcp.server import mcp, register_tools
from tests.llm_kontrakt_support import client_session

READ = (True, False, True, False)
MARK = (False, False, True, False)
ADD = (False, False, False, False)
DESTRUCTIVE = (False, True, False, False)
SEND = (False, True, False, True)

EXPECTED = {
    "list_mailboxes": READ,
    "get_mailbox_status": READ,
    "list_emails": READ,
    "get_email": READ,
    "get_email_headers": READ,
    "search_emails": READ,
    "get_thread": READ,
    "check_new_emails": READ,
    "wait_for_new_email": READ,
    "get_attachment": ADD,
    "mark_email_read": MARK,
    "mark_email_unread": MARK,
    "flag_email": MARK,
    "unflag_email": MARK,
    "add_label": MARK,
    "remove_label": (False, True, True, False),
    "move_email": DESTRUCTIVE,
    "delete_email": DESTRUCTIVE,
    "create_folder": ADD,
    "delete_folder": DESTRUCTIVE,
    "rename_folder": DESTRUCTIVE,
    "create_draft": ADD,
    "create_reply_draft": ADD,
    "create_forward_draft": ADD,
    "update_draft": DESTRUCTIVE,
    "send_draft": SEND,
    "send_email": SEND,
    "reply_to_email": SEND,
    "forward_email": SEND,
}


@pytest.fixture
async def tools(monkeypatch):
    async with client_session(monkeypatch) as session:
        return {t.name: t for t in (await session.list_tools()).tools}


async def test_every_tool_is_classified_in_the_table(tools):
    assert set(tools) == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
async def test_tool_hints_follow_the_table(tools, name):
    ann = tools[name].annotations
    assert ann is not None, f"{name} saknar annotations"
    actual = (ann.readOnlyHint, ann.destructiveHint, ann.idempotentHint, ann.openWorldHint)
    assert actual == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
async def test_tool_has_a_title(tools, name):
    tool = tools[name]
    assert tool.title and tool.title.strip()
    assert tool.annotations.title == tool.title


async def test_titles_are_unique(tools):
    titles = [t.title for t in tools.values()]
    assert len(titles) == len(set(titles))


def test_register_helper_requires_explicit_classification():
    from protonmail_mcp.tools import tool

    with pytest.raises(TypeError):
        tool("Utan klassning")  # alla fyra klassningar måste anges


def test_register_helper_returns_the_function_unchanged():
    from protonmail_mcp.tools import messages

    register_tools()
    # Testerna anropar verktygsfunktionerna direkt; dekoratorn byter inte ut dem
    assert not hasattr(messages.get_email, "__wrapped__")
    assert inspect.unwrap(mcp._tool_manager.get_tool("get_email").fn) is messages.get_email
