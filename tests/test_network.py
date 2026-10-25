import network_link as nl

BODY = """var known_device_list=[
{mac:'d2%3Afd%3A7c%3Aa1%3A96%3A1f',hostname:'Pixel-9',ip:'192.168.1.135',activity:'1',os:'Android'},
{mac:'f6%3Aed%3A43%3A19%3Afe%3Ade',hostname:'Pixel-9-Pro-XL',ip:'192.168.1.183',activity:'0',os:'Linux'},
{mac:'40%3Ae2%3A30%3Ae2%3A3d%3A9f',hostname:'Claude',ip:'192.168.1.198',activity:'1',os:'Windows 10'}];
var rate=[{timestamp:'0',app:'4294967295',mac:'40%3Ae2%3A30%3Ae2%3A3d%3A9f',tx:'1000',rx:'5000000'}];"""


def make():
    return nl.HomeNetwork("192.168.1.254", {"James": "D2:FD:7C:A1:96:1F", "Claire": "f6:ed:43:19:fe:de"},
                          {"Claude PC": "40:e2:30:e2:3d:9f"})


def test_parse_hub():
    d = nl.parse_hub(BODY)
    assert d["d2:fd:7c:a1:96:1f"]["connected"] is True
    assert d["f6:ed:43:19:fe:de"]["connected"] is False
    assert d["40:e2:30:e2:3d:9f"]["rx"] == 5000000 and d["40:e2:30:e2:3d:9f"]["name"] == "Claude"


def test_who_is_home():
    net = make()
    net.update(nl.parse_hub(BODY), 1000)
    people = {p["name"]: p["home"] for p in net.snapshot()["people"]}
    assert people == {"James": True, "Claire": False}


def test_phone_nap_isnt_out():
    net = make()
    net.update(nl.parse_hub(BODY), 1000)
    gone = BODY.replace("ip:'192.168.1.135',activity:'1'", "ip:'192.168.1.135',activity:'0'")
    net.update(nl.parse_hub(gone), 1000 + 5 * 60)            # 5 minutes off the Wi-Fi: still home
    assert net.snapshot()["people"][0]["home"] is True
    net.update(nl.parse_hub(gone), 1000 + 11 * 60)           # 11 minutes: out, since he was last seen
    james = net.snapshot()["people"][0]
    assert james["home"] is False and james["since"] == 1000
    net.update(nl.parse_hub(BODY), 2000)                     # back
    james = net.snapshot()["people"][0]
    assert james["home"] is True and james["since"] == 2000


def test_computer_busy():
    net = make()
    net.update(nl.parse_hub(BODY), 1000)
    busier = BODY.replace("rx:'5000000'", "rx:'95000000'")   # 90 MB in 30 seconds = 24 Mbit/s
    net.update(nl.parse_hub(busier), 1030)
    pc = net.snapshot()["computers"][0]
    assert pc["on"] and pc["busy"] and pc["mbps"] == 24.0


def test_hub_details():
    body = ("{mac:'b8%3A27%3Aeb%3A6b%3Ac4%3A7d',hostname:'raspberrypi',ip:'192.168.1.98',activity:'0',"
            "time_last_active:'2026/10/25 20:23:18',port:'eth1'}")
    d = nl.parse_hub(body)["b8:27:eb:6b:c4:7d"]
    assert d["link"] == "Cable" and d["last_seen"] is not None
    net = nl.HomeNetwork("hub", {}, {"Raspberry Pi": "b8:27:eb:6b:c4:7d"})
    net.update(nl.parse_hub(body), 1000)
    pi = net.snapshot()["computers"][0]
    assert pi["on"] is False and pi["last_seen"] and pi["ip"] is None


def test_this_computer_stats():
    stats, macs = nl.this_computer()
    if stats is not None:
        assert 0 <= stats["cpu"] <= 100 and stats["uptime"] > 0


def test_helper_figures(tmp_path):
    import asyncio, aiohttp
    from aiohttp import web

    async def stats(request):
        return web.json_response({"cpu": 7, "memory": 40, "disk_free_gb": 12, "disk_used": 60,
                                  "uptime": 3600, "temp": 52.1})

    async def main():
        app = web.Application(); app.router.add_get("/stats", stats)
        runner = web.AppRunner(app); await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", 8097).start()
        net = nl.HomeNetwork("hub", {}, {"Raspberry Pi": "b8:27:eb:6b:c4:7d", "Laptop": "aa:aa:aa:aa:aa:aa"})
        body = ("{mac:'b8%3A27%3Aeb%3A6b%3Ac4%3A7d',hostname:'raspberrypi',ip:'127.0.0.1',activity:'1'}"
                "{mac:'aa%3Aaa%3Aaa%3Aaa%3Aaa%3Aaa',hostname:'laptop',ip:'127.0.0.9',activity:'1'}")
        net.update(nl.parse_hub(body), 1000)
        async with aiohttp.ClientSession() as s:
            await net._ask_helpers(s)
        await runner.cleanup()
        return net.snapshot()["computers"]

    pi, laptop = asyncio.run(main())
    assert pi["stats"]["temp"] == 52.1 and pi["stats"]["disk_free_gb"] == 12
    assert "stats" not in laptop      # no helper there
