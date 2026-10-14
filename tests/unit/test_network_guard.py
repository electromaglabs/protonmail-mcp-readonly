"""Enhetstester får aldrig nå en riktig ProtonMail Bridge.

En mock som av misstag faller igenom till en riktig anslutning ska ge ett
tydligt fel, inte inloggningsförsök mot Bridge på den här maskinen.
"""
import asyncio

import pytest


@pytest.mark.parametrize("port", [1143, 1026])
async def test_connection_to_bridge_port_is_blocked(port):
    with pytest.raises(ConnectionRefusedError, match="blockerad i tester"):
        await asyncio.open_connection("127.0.0.1", port)


async def test_other_local_ports_are_allowed():
    async def handle(reader, writer):
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        _, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.close()
