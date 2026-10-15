"""Kontrollerat skrivtest mot riktiga Bridge, i två steg. Körs bara för hand.

    steg 1:  uv run python tests/manual/livetest.py steg1
    steg 2:  uv run python tests/manual/livetest.py steg2 MCPLIVE<tid>

Steg 1 skapar en testmapp Folders/MCPLIVE<tid> och en testetikett
Labels/MCPLIVE<tid>etikett, skickar mejl till det egna kontot
(PROTONMAIL_USERNAME, aldrig någon annan adress) med token i ämnet och kör
verktygen via MCP-stdio mot koden i det här repot. Inget raderas: steg 1
slutar med en förteckning över vad som finns var, så att man kan titta i
Proton innan steg 2 städar.

Steg 2 rör bara objekt vars ämne eller namn innehåller den angivna token:
avmarkerar, flyttar mejl till Trash, raderar dem permanent därifrån, raderar
utkast, tar bort testmappen och testetiketten, raderar föräldralösa utkast i
All Mail och kontrollerar till sist att inget med token finns kvar i någon vy.

Inställningarna (PROTONMAIL_USERNAME/PASSWORD …) läses som av servern, ur
miljön eller .env. Skriptet innehåller inga hemligheter.
"""
from __future__ import annotations

import asyncio
import email
import email.policy
import json
import os
import re
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from protonmail_mcp.config import get_settings
from protonmail_mcp.imap_client import IMAPClient

REPO = Path(__file__).resolve().parents[2]
MAX_SENT = 20
VIEWS = ("INBOX", "Sent", "Drafts", "Trash", "Starred", "Archive", "Spam", "All Mail")
os.environ["PROTONMAIL_WATCH_ENABLED"] = "false"

results: list[tuple[str, bool, str]] = []
sent = 0


def log(step: str, ok: bool, info: str = "") -> None:
    results.append((step, ok, info))
    print(f"{'OK  ' if ok else 'FEL '} {step}  {info}"[:400], flush=True)


class Live:
    """MCP-session mot servern plus en egen IMAP-anslutning för läsning."""

    def __init__(self, token: str, call, imap: IMAPClient) -> None:
        self.token, self.call_tool, self.imap = token, call, imap
        self.me = get_settings().username

    async def call(self, tool: str, **args):
        return await self.call_tool(tool, **args)

    async def find(self, mailbox: str, extra: str = "", want: int = 1, tries: int = 20, exact: str | None = None):
        """Mejl i mailbox vars ämne innehåller token (+extra); väntar på leverans."""
        hits: list[dict] = []
        for _ in range(tries):
            res = await self.call("search_emails", mailbox=mailbox, subject=self.token + extra, max_results=50)
            hits = [m for m in res["messages"] if self.token in (m.get("subject") or "")
                    and (exact is None or m["subject"] == exact)]
            if len(hits) >= want:
                return hits
            await asyncio.sleep(3)
        return hits

    async def ensure(self, mailbox: str, uids: list[str]) -> None:
        """Vägrar skriva om något av UID:na saknar token i ämnet."""
        for uid in uids:
            hdr = await self.call("get_email_headers", uid=uid, mailbox=mailbox)
            if self.token not in (hdr.get("subject") or ""):
                raise RuntimeError(f"VÄGRAR skriva: UID {uid} i {mailbox} har ämnet {hdr.get('subject')!r}")

    async def send(self, **args):
        global sent
        if sent >= MAX_SENT:
            raise RuntimeError("Högst 20 skickade mejl")
        assert self.token in args.get("subject", self.token)
        sent += 1
        return await self.call("send_email", to=self.me, **args)

    async def inventory(self, folder: str, label: str) -> dict[str, list[str]]:
        out = {}
        for mb in (*VIEWS, folder, label):
            try:
                r = await self.imap.search_messages(mb, subject=self.token, max_results=50)
                out[mb] = [f"{m['uid']}: {m['subject']} {m['flags']}" for m in r["messages"]
                           if self.token in (m.get("subject") or "")]
            except ValueError as exc:
                out[mb] = [f"(finns inte: {exc})"]
        return out

    async def raw(self, mailbox: str, uid: str) -> email.message.Message:
        data = await self.imap.get_message(mailbox, uid)
        return email.message_from_bytes(data or b"", policy=email.policy.compat32)


def _pm_headers(msg) -> list[tuple[str, str]]:
    return [(k.lower(), str(v)) for k, v in msg.items() if k.lower().startswith("x-pm-")]


def _parse_result(res) -> object:
    txt = res.content[0].text if res.content else ""
    if res.isError:
        raise RuntimeError(txt)
    sc = getattr(res, "structuredContent", None)
    if sc is not None:
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    try:
        return json.loads(txt)
    except ValueError:
        return txt


async def run(step, token: str) -> None:
    params = StdioServerParameters(
        command="uv", args=["--directory", str(REPO), "run", "protonmail-mcp"], env={**os.environ}
    )
    imap = IMAPClient(get_settings())
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            async def call(tool, **a):
                return _parse_result(await s.call_tool(tool, a))

            try:
                await step(Live(token, call, imap))
            finally:
                await imap.disconnect()


# ---------------------------------------------------------------- steg 1
async def steg1(lv: Live) -> None:
    t = lv.token
    folder, label = f"Folders/{t}", f"Labels/{t}etikett"
    att = Path(os.path.expanduser("~/Downloads/protonmail-mcp")) / f"{t}.txt"
    try:
        await lv.call("create_folder", name=folder); log("create_folder (mapp)", True, folder)
        await lv.call("create_folder", name=label); log("create_folder (etikett)", True, label)
        names = [m["name"] for m in await lv.call("list_mailboxes")]
        log("list_mailboxes visar båda", folder in names and label in names)

        # L5: namnet används redan av etiketten
        try:
            await lv.call("create_folder", name=f"Folders/{t}etikett")
            log("L5 upptaget namn ger fel", False, "skapades!")
        except RuntimeError as exc:
            text = str(exc)
            log("L5 upptaget namn ger begripligt fel", "unika" in text and label in text, text[:300])

        att.parent.mkdir(parents=True, exist_ok=True)
        att.write_text("Bilaga från skrivtestet åäö\n", encoding="utf-8")
        r1 = await lv.send(subject=f"{t} A åäö", body="Testmejl A från skrivtestet.", attachments=[att.name])
        log("send_email med bilaga", r1 is True, str(r1))
        r2 = await lv.send(subject=f"{t} B", body="Testmejl B från skrivtestet.")
        log("send_email", r2 is True, str(r2))
        hits = await lv.find("INBOX", want=2)
        log("mejlen kom fram i INBOX", len(hits) >= 2, f"{len(hits)} st")
        a = next(m for m in hits if m["subject"] == f"{t} A åäö")
        b = next(m for m in hits if m["subject"] == f"{t} B")
        ua, ub = a["uid"], b["uid"]

        e = await lv.call("get_email", uid=ua, mailbox="INBOX")
        log("get_email", t in e["subject"], f"bilagor={len(e['attachments'])}")
        ga = await lv.call("get_attachment", uid=ua, mailbox="INBOX", index=0, save=False)
        log("get_attachment save=False", "åäö" in json.dumps(ga, ensure_ascii=False))

        await lv.ensure("INBOX", [ua])
        await lv.call("mark_email_read", uid=ua, mailbox="INBOX")
        await lv.call("mark_email_unread", uid=ua, mailbox="INBOX")
        log("mark_read/unread", True)

        # L1: stjärna av och på, Starred-vyn direkt efter unflag
        await lv.call("flag_email", uid=ua, mailbox="INBOX")
        starred = await lv.find("Starred", " A")
        log("flag_email → syns i Starred", any(m["subject"] == a["subject"] for m in starred))
        await lv.call("unflag_email", uid=ua, mailbox="INBOX")
        st = await lv.call("search_emails", mailbox="Starred", subject=t)
        log("L1 unflag_email → borta ur Starred direkt", st["total"] == 0,
            f"kvar={st['total']} {[m.get('flags') for m in st['messages']]}")
        inbox_a = await lv.find("INBOX", " A", exact=a["subject"])
        log("L1 mejlet ligger kvar i INBOX utan \\Flagged",
            bool(inbox_a) and "\\Flagged" not in inbox_a[0]["flags"], str(inbox_a[:1]))
        await asyncio.sleep(45)
        st = await lv.call("search_emails", mailbox="Starred", subject=t)
        inbox_a = await lv.find("INBOX", " A", exact=a["subject"])
        log("L1 efter Bridges synk (45 s): fortfarande borta ur Starred, kvar i INBOX",
            st["total"] == 0 and bool(inbox_a) and "\\Flagged" not in inbox_a[0]["flags"],
            f"Starred={st['total']} INBOX={[m['flags'] for m in inbox_a]}")

        await lv.call("add_label", uid=ua, mailbox="INBOX", label=label)
        log("add_label → syns i etiketten", len(await lv.find(label, " A")) >= 1)
        await lv.call("remove_label", uid=ua, mailbox="INBOX", label=label)
        gone = await lv.call("search_emails", mailbox=label, subject=t + " A")
        log("remove_label → borta ur etiketten", gone["total"] == 0, f"kvar={gone['total']}")
        await lv.ensure("INBOX", [ub])
        await lv.call("add_label", uid=ub, mailbox="INBOX", label=label)
        log("add_label B (ligger kvar med etiketten)", len(await lv.find(label, " B")) >= 1)

        bulk = await lv.call("mark_email_read", uid=[ua, ub], mailbox="INBOX")
        log("massoperation mark_email_read [A,B]", len(bulk.get("ok", [])) == 2, str(bulk))
        mv = await lv.call("move_email", uid=[ua, ub], mailbox="INBOX", target_mailbox=folder)
        log("move_email [A,B] → testmapp", len(mv.get("ok", [])) == 2, str(mv))
        in_folder = await lv.find(folder, want=2)
        left = await lv.call("search_emails", mailbox="INBOX", subject=t)
        log("flytten: 2 i mappen, 0 kvar i INBOX", len(in_folder) >= 2 and left["total"] == 0,
            f"mapp={len(in_folder)} inbox={left['total']}")
        fa = next(m for m in in_folder if m["subject"] == a["subject"])
        fb = next(m for m in in_folder if m["subject"] == b["subject"])

        # L4: svar på mejl från mig till mig
        global sent
        sent += 1
        try:
            await lv.call("reply_to_email", uid=fb["uid"], mailbox=folder, body="Svar från skrivtestet.")
            reply = await lv.find("INBOX", " B", exact=f"Re: {t} B")
            log("L4 reply_to_email på mejl till mig själv kom fram", bool(reply), str([m["subject"] for m in reply]))
        except RuntimeError as exc:
            reply = []
            log("L4 reply_to_email på mejl till mig själv", False, str(exc)[-200:])
        if reply:
            await lv.ensure("INBOX", [reply[0]["uid"]])
            await lv.call("flag_email", uid=reply[0]["uid"], mailbox="INBOX")
            log("svaret stjärnmärkt (ligger kvar i Starred)", bool(await lv.find("Starred", " B")))
        th = await lv.call("get_thread", uid=fb["uid"], mailbox=folder, max_messages=10)
        log("get_thread", len(th["messages"]) >= 1, f"{len(th['messages'])} st, complete={th.get('complete')}")

        d = await lv.call("create_draft", to=lv.me, subject=f"{t} utkast", body="Utkast v1")
        log("create_draft ger uid (APPENDUID)", d.get("uid") is not None, str(d))
        d2 = await lv.call("update_draft", uid=d["uid"], mailbox="Drafts", to=lv.me, subject=f"{t} utkast", body="Utkast v2")
        log("update_draft (v1 till Trash)", d2.get("uid") is not None, str(d2)[:200])

        # L6: svarsutkast
        rd = await lv.call("create_reply_draft", uid=fa["uid"], mailbox=folder, body="Svarsutkast")
        log("L6 create_reply_draft", rd.get("uid") is not None, str(rd)[:200])
        if rd.get("uid"):
            de = await lv.call("get_email", uid=rd["uid"], mailbox="Drafts")
            log("L6 svarsutkastet: Re:-ämne och mottagare = mig själv",
                de["subject"] == f"Re: {a['subject']}" and any(lv.me.lower() in x.lower() for x in de["to"]),
                f"{de['subject']!r} to={de['to']}")

        # L6: send_draft hela vägen. Skickat till sig själv blir utkastet självt det
        # skickade mejlet i Proton (samma Proton-id och Message-ID), så X-Pm-värdena
        # kan inte jämföras med utkastets. Kontrollen: samma uppsättning X-Pm-rubriker
        # som ett vanligt skickat mejl och inga dubbletter (send_draft tar bort
        # utkastets X-Pm-* före skicket; Bridge lägger egna på varje mejl vid FETCH).
        sent += 1
        sd = await lv.call("send_draft", uid=d2["uid"], mailbox="Drafts")
        log("L6 send_draft", sd.get("draft_deleted") is not False, str(sd)[:250])
        got = await lv.find("INBOX", " utkast", exact=f"{t} utkast")
        log("L6 skickat utkast kom fram i INBOX", bool(got))
        if got:
            names = [k for k, _ in _pm_headers(await lv.raw("INBOX", got[0]["uid"]))]
            base = await lv.find("INBOX", " B", exact=f"Re: {t} B")
            base_names = sorted({k for k, _ in _pm_headers(await lv.raw("INBOX", base[0]["uid"]))}) if base else []
            log("L6 X-Pm-rubrikerna hos mottagaren som för ett vanligt mejl, inga dubbletter",
                len(names) == len(set(names)) and sorted(set(names)) == base_names,
                f"mottagen={sorted(names)} vanligt={base_names}")
        drafts_left = await lv.call("search_emails", mailbox="Drafts", subject=f"{t} utkast")
        log("L6 utkastet borta ur Drafts efter send_draft",
            not [m for m in drafts_left["messages"] if m["subject"] == f"{t} utkast"],
            f"kvar={[m['subject'] for m in drafts_left['messages']]}")
    except Exception as exc:  # noqa: BLE001
        log("AVBRUTET", False, f"{type(exc).__name__}: {exc}")

    print(f"\n=== FÖRTECKNING (token {t}) ===")
    print(f"testmapp: {folder}\ntestetikett: {label}\nbilaga: {att}")
    for mb, items in (await lv.inventory(folder, label)).items():
        print(f"  {mb}: {items}")
    print(f"\nSkickade mejl i körningen: {sent}")
    print("steg 1 klart — väntar på godkännande innan städning")
    print(f"Städa med: uv run python tests/manual/livetest.py steg2 {t}")


# ---------------------------------------------------------------- steg 2
async def steg2(lv: Live) -> None:
    t = lv.token
    folder, label = f"Folders/{t}", f"Labels/{t}etikett"

    async def uids(mb):
        res = await lv.call("search_emails", mailbox=mb, subject=t, max_results=50)
        return [m["uid"] for m in res["messages"] if t in (m.get("subject") or "")]

    async def step(name, coro):
        try:
            log(name, True, str(await coro)[:250])
        except Exception as exc:  # noqa: BLE001
            log(name, False, f"{type(exc).__name__}: {exc}"[:300])

    names = [m["name"] for m in await lv.call("list_mailboxes")]
    if u := await uids("Starred"):
        await lv.ensure("Starred", u)
        await step("unflag i Starred", lv.call("unflag_email", uid=u, mailbox="Starred"))
    if u := await uids("Drafts"):
        await lv.ensure("Drafts", u)
        await step("utkast permanent ur Drafts", lv.call("delete_email", uid=u, mailbox="Drafts", permanent=True))
    # Ett mejl till sig själv är ETT mejl i INBOX (eller mappen) och Sent. Flytta
    # först från mappen/INBOX och vänta tills Bridge synkat Sent-vyn — annars
    # träffar flytten från Sent ett mejl som redan ligger i Trash (Code=2501).
    for mb in (folder, "INBOX", "Archive"):
        if mb in names or mb in ("INBOX", "Archive"):
            if u := await uids(mb):
                await lv.ensure(mb, u)
                await step(f"till Trash från {mb}", lv.call("delete_email", uid=u, mailbox=mb))
    for _ in range(20):
        if not await uids("Sent"):
            break
        await asyncio.sleep(3)
    if u := await uids("Sent"):
        await lv.ensure("Sent", u)
        await step("till Trash från Sent", lv.call("delete_email", uid=u, mailbox="Sent"))
    await asyncio.sleep(3)
    if u := await uids("Trash"):
        await lv.ensure("Trash", u)
        await step("permanent ur Trash", lv.call("delete_email", uid=u, mailbox="Trash", permanent=True))
    for name in (folder, label):
        if name in names:
            await step(f"delete_folder {name}", lv.call("delete_folder", name=name, force=True))
    try:
        (Path(os.path.expanduser("~/Downloads/protonmail-mcp")) / f"{t}.txt").unlink()
    except OSError:
        pass

    # Bridges All Mail följer med vid nästa händelsehämtning (20–40 s)
    print("väntar 50 s på Bridges synk …", flush=True)
    await asyncio.sleep(50)
    leftovers = await lv.imap.search_messages("All Mail", subject=t, max_results=50)
    orphans = [m for m in leftovers["messages"] if t in (m.get("subject") or "") and "\\Draft" in m["flags"]]
    for m in orphans:
        await _delete_orphan(lv, m)
    if orphans:
        await asyncio.sleep(45)

    inv = await lv.inventory(folder, label)
    rest = {mb: items for mb, items in inv.items() if items and not items[0].startswith("(finns inte")}
    left_folders = [m["name"] for m in await lv.call("list_mailboxes") if t in m["name"]]
    log("inga mejl med token kvar i någon vy (inkl. All Mail)", not rest, str(rest))
    log("inga testmappar/-etiketter kvar", not left_folders, str(left_folders))


async def _delete_orphan(lv: Live, m: dict) -> None:
    """Föräldralöst utkast i All Mail: COPY till Trash, sedan permanent där (bara detta UID)."""
    imap = lv.imap
    if lv.token not in m["subject"]:
        raise RuntimeError(f"VÄGRAR: {m['subject']!r}")
    await imap._ensure_connected()
    await imap._select("All Mail")
    resp = await imap._uid("copy", m["uid"], '"Trash"')
    log(f"föräldralöst utkast {m['uid']} → Trash", resp.result == "OK", m["subject"])
    await asyncio.sleep(3)
    res = await lv.call("search_emails", mailbox="Trash", subject=m["subject"])
    u = [x["uid"] for x in res["messages"] if x["subject"] == m["subject"]]
    if u:
        await lv.ensure("Trash", u)
        out = await lv.call("delete_email", uid=u, mailbox="Trash", permanent=True)
        log("föräldralöst utkast permanent ur Trash", not out.get("failed"), str(out)[:200])


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "steg1":
        token = f"MCPLIVE{int(time.time())}"
        print("TOKEN", token, flush=True)
        asyncio.run(run(steg1, token))
    elif len(sys.argv) == 3 and sys.argv[1] == "steg2" and re.fullmatch(r"MCPLIVE\d+", sys.argv[2]):
        asyncio.run(run(steg2, sys.argv[2]))
    else:
        sys.exit(__doc__)
    fails = [r for r in results if not r[1]]
    print(f"\n=== SAMMANFATTNING === {len(results) - len(fails)} OK, {len(fails)} FEL")
    for name, _, info in fails:
        print(" FEL:", name, info[:250])


if __name__ == "__main__":
    main()
