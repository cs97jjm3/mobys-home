"""Tests for the TV and console checks, using pretend devices on this computer."""

import asyncio
import struct

import devices_link as dl


def test_reads_ps5_replies():
    on = b"HTTP/1.1 200 Ok\nhost-id:ABC\nhost-type:PS5\nhost-name:PS5-123\nrunning-app-name:F1 25\n"
    rest = b"HTTP/1.1 620 Server Standby\nhost-id:ABC\nhost-type:PS5\nhost-name:PS5-123\n"
    assert dl.parse_ps5(on) == {"state": "on", "game": "F1 25", "name": "PS5-123"}
    assert dl.parse_ps5(rest)["state"] == "rest"


def test_xbox_search_packet_and_reply():
    assert dl.XBOX_SEARCH.hex() == "dd00000a0000" + "00000000" + "0008" + "0000" + "0002"
    name = "Ed's Xbox".encode()
    reply = struct.pack(">HHH", 0xDD01, 0, 2) + struct.pack(">IH", 0, 1) \
        + struct.pack(">H", len(name)) + name + b"\x00" + b"rest-of-packet"
    assert dl.parse_xbox(reply) == "Ed's Xbox"
    assert dl.parse_xbox(b"\x00\x01") is None


def test_wake_on_lan_needs_a_mac():
    try:
        dl.wake_on_lan("")
    except ValueError:
        return
    raise AssertionError("expected a ValueError")


class Responder(asyncio.DatagramProtocol):
    def __init__(self, reply, need_port=None):
        self.reply, self.need_port = reply, need_port

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if self.need_port and addr[1] != self.need_port:
            return
        self.transport.sendto(self.reply, addr)


def test_asks_a_pretend_ps5_from_the_right_port():
    async def main():
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: Responder(b"HTTP/1.1 200 Ok\nrunning-app-name:Gran Turismo 7\n",
                              need_port=dl.PS5_LOCAL_PORT),
            local_addr=("127.0.0.1", 0))
        port = transport.get_extra_info("sockname")[1]
        try:
            reply = await dl.udp_ask("127.0.0.1", port, dl.PS5_SEARCH, local_port=dl.PS5_LOCAL_PORT)
            assert dl.parse_ps5(reply)["game"] == "Gran Turismo 7"
            silent = await dl.udp_ask("127.0.0.1", port + 1, b"hello", timeout=0.3, tries=1)
            assert silent is None
        finally:
            transport.close()
    asyncio.run(main())


def test_tv_keeps_connection_open(tmp_path):
    import asyncio
    import devices_link as dl

    class Fake:
        opened = 0
        def open(self): Fake.opened += 1
        def close(self): pass
        def send_key(self, key):
            if key == "BROKEN":
                raise ConnectionError("dropped")
            return key

    tv = dl.SamsungTV("1.2.3.4", "", tmp_path / "token.txt")
    tv._remote = lambda timeout=8: Fake()

    async def go():
        await tv._run(lambda r: r.send_key("KEY_VOLUP"))
        await tv._run(lambda r: r.send_key("KEY_VOLUP"))
        assert Fake.opened == 1                      # second press reused the connection
        try:
            await tv._run(lambda r: r.send_key("BROKEN"))
        except ConnectionError:
            pass
        assert Fake.opened == 2                      # dropped: reopened once, then gave up
        assert await tv._run(lambda r: r.send_key("KEY_MUTE")) == "KEY_MUTE"
    asyncio.run(go())
