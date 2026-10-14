"""IMAPClient.create_folder/rename_folder/delete_folder: Protons regler för mappnamn."""
import pytest

from tests.fix_flytta_bridge import make_client


@pytest.fixture
def imap_and_bridge(monkeypatch):
    return make_client(monkeypatch)


class TestCreateFolder:
    @pytest.mark.parametrize("name", ["Folders/Projekt", "Labels/Kvitton", "Folders/A/B", "Labels/A\\/B"])
    async def test_accepts_prefixed_names(self, imap_and_bridge, name):
        imap, bridge = imap_and_bridge
        assert await imap.create_folder(name) is True
        assert len(bridge.sent("CREATE")) == 1

    @pytest.mark.parametrize("name", ["Projekt", "INBOX", "folders/x", "Folders", "Labels", "Folders/", "Labels/"])
    async def test_rejects_without_prefix_or_name(self, imap_and_bridge, name):
        imap, bridge = imap_and_bridge
        with pytest.raises(ValueError, match="Folders/"):
            await imap.create_folder(name)
        assert bridge.commands == []

    async def test_rejects_sub_label(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        with pytest.raises(ValueError, match="Underetiketter"):
            await imap.create_folder("Labels/Jobb/Kunder")
        assert bridge.commands == []

    async def test_no_raises_with_server_text(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.refuse["CREATE"] = "parent folder does not exist"
        with pytest.raises(ValueError, match="parent folder does not exist"):
            await imap.create_folder("Folders/A/B")

    async def test_nested_folder_error_mentions_parent(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.refuse["CREATE"] = "operation not allowed"
        with pytest.raises(ValueError, match="Folders/A"):
            await imap.create_folder("Folders/A/B")


class TestRenameFolder:
    async def test_renames_within_type(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        assert await imap.rename_folder("Folders/A", "Folders/B") is True
        assert bridge.sent("RENAME") == [("RENAME", "Folders/A", "Folders/B")]

    @pytest.mark.parametrize("old,new", [
        ("Folders/A", "Labels/A"), ("Labels/A", "Folders/A"),
    ])
    async def test_rejects_between_types(self, imap_and_bridge, old, new):
        imap, bridge = imap_and_bridge
        with pytest.raises(ValueError, match="mellan mapp och etikett"):
            await imap.rename_folder(old, new)
        assert bridge.commands == []

    @pytest.mark.parametrize("old,new", [
        ("INBOX", "Folders/Inkorg"), ("Folders/A", "B"), ("Trash", "Labels/x"),
    ])
    async def test_rejects_unprefixed(self, imap_and_bridge, old, new):
        imap, bridge = imap_and_bridge
        with pytest.raises(ValueError, match="Folders/"):
            await imap.rename_folder(old, new)
        assert bridge.commands == []

    async def test_rejects_sub_label(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        with pytest.raises(ValueError, match="Underetiketter"):
            await imap.rename_folder("Labels/A", "Labels/A/B")

    async def test_no_raises(self, imap_and_bridge):
        imap, bridge = imap_and_bridge
        bridge.refuse["RENAME"] = "no such mailbox"
        with pytest.raises(ValueError, match="no such mailbox"):
            await imap.rename_folder("Folders/A", "Folders/B")


class TestDeleteFolderNames:
    @pytest.mark.parametrize("name", ["INBOX", "Trash", "All Mail", "Folders", "Labels", "Projekt"])
    async def test_rejects_system_and_unprefixed(self, imap_and_bridge, name):
        imap, bridge = imap_and_bridge
        with pytest.raises(ValueError, match="Folders/"):
            await imap.delete_folder(name)
        assert bridge.commands == []
