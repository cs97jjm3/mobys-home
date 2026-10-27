// Moby's Home demo: a pretend house, so the real page runs without a real home behind it.
// Everything here is made up. Nothing is sent anywhere.
(function () {
  const now = () => Date.now() / 1000;
  const start = now();
  const wait = ms => new Promise(r => setTimeout(r, ms));

  const SONGS = [
    ["Fenland Morning", "The Low Skies · Demo Radio"],
    ["Slow Train to March", "Ouse & Nene · Demo Radio"],
    ["Strawberry Fields Road", "The Wisbech Ramblers · Demo Radio"],
    ["Kettle On", "Moby & the Echos · Demo Radio"],
  ];

  function weather() {
    const hourNow = new Date(); hourNow.setMinutes(0, 0, 0);
    const icons = ["part", "part", "cloud", "cloud", "drizzle", "rain", "rain", "cloud", "part", "clear", "clear", "clear"];
    const rain = [5, 10, 20, 35, 55, 70, 65, 30, 15, 5, 5, 0];
    const hours = icons.map((icon, i) => {
      const t = new Date(hourNow.getTime() + i * 3600e3);
      const night = t.getHours() >= 18 || t.getHours() < 7;
      return { time: t.toTimeString().slice(0, 5), temp: 11.5 - i * 0.4, rain: rain[i],
               icon: night && (icon === "part" || icon === "clear") ? icon + "-night" : icon, text: "" };
    });
    const days = [["part", 12, 6, 60], ["rain", 10, 5, 80], ["showers", 11, 4, 55], ["part", 13, 7, 20],
                  ["clear", 14, 6, 5], ["cloud", 12, 8, 30]].map(([icon, high, low, r], i) => ({
      day: i === 0 ? "Today" : new Date(Date.now() + i * 86400e3).toLocaleDateString("en-GB", { weekday: "short" }),
      high, low, rain: r, icon, text: "", sunrise: "06:52", sunset: "16:44" }));
    const firstWet = hours.find(h => h.rain >= 50);
    return { now: { temp: 11.6, feels: 9.2, wind: 12, gusts: 25, text: "Partly cloudy", icon: "part" },
             hours, days, today: days[0], rain_note: firstWet ? `Rain likely from ${firstWet.time}` : "Dry for the next 12 hours",
             measured: [{ name: "Marham", temp: 9, km: 27, time: start - 900 },
                        { name: "Cambridge", temp: 11, km: 51, time: start - 900 },
                        { name: "Norwich", temp: 11, km: 76, time: start - 900 }],
             error: null, updated: start };
  }

  const house = {
    switches: [
      { id: "1", name: "Lounge lamp", label: "Light", reachable: true, power: "ON", can_dim: true, brightness: 60 },
      { id: "2", name: "Kitchen lights", label: "Light", reachable: true, power: "ON", can_dim: true, brightness: 100 },
      { id: "3", name: "Fish tank", label: "Light", reachable: true, power: "ON" },
      { id: "4", name: "Landing", label: "Light", reachable: true, power: "ON", can_dim: true, brightness: 80,
        can_colour: true, can_white: true, hue: 272, saturation: 1 },
      { id: "5", name: "Office plug", label: "Plug", reachable: true, power: "OFF" },
      { id: "6", name: "Kettle plug", label: "Plug", reachable: true, power: "OFF" },
      { id: "7", name: "Bedroom lamp", label: "Light", reachable: true, power: "OFF", can_dim: true, brightness: 30 },
      { id: "8", name: "Christmas tree", label: "Plug", reachable: false },
    ],
    sensors: [
      { id: "s1", name: "Front door", kind: "CAMERA", reachable: true, motion: "NOT_DETECTED", motion_changed: start - 47 * 60 },
      { id: "s2", name: "House alarm", kind: "SECURITY_PANEL", maker: "Alarm", reachable: true },
    ],
    rooms: [{ name: "Office Dot", lux: 140 }, { name: "Bedroom Dot", lux: 6 }],
    echos: [
      { serial: "e1", name: "Kitchen Show", model: "Echo Show 8", online: true, has_media: true, playing: true, song: 0,
        volume: 40, dnd: false, next: { kind: "Timer", label: "pasta", at: start + 9 * 60 } },
      { serial: "e2", name: "Lounge Echo", model: "Echo", online: true, has_media: false, volume: 30, dnd: false, next: null },
      { serial: "e3", name: "Office Dot", model: "Echo Dot", online: true, has_media: false, volume: 25, dnd: false, next: null },
      { serial: "e4", name: "Bedroom Dot", model: "Echo Dot", online: true, has_media: false, volume: 15, dnd: true,
        next: { kind: "Alarm", label: "work", at: (() => { const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(6, 45, 0, 0); return d / 1000; })() } },
      { serial: "e5", name: "Garage Dot", model: "Echo Dot", online: false },
    ],
    routines: ["Good morning", "Goodnight", "Film night", "Sunset lights", "Leaving the house"],
    tv: { state: "on", label: "Samsung TV", model: "55\" Crystal UHD", watching: "BT TV · streaming", needs_allow: false,
          apps: ["Netflix", "YouTube", "BBC iPlayer", "Prime Video", "Disney+", "ITVX"].map((name, i) => ({ id: String(i), name })) },
    ps5: { state: "on", label: "PS5", game: "F1 25", game_icon: null, psn_warning: null },
    xbox: { state: "asleep", label: "Xbox" },
    casts: [
      { id: "c1", name: "Bedroom TV", model: "Chromecast", online: true, app: "Spotify", state: "playing",
        title: "Kettle On", subtitle: "Moby & the Echos", art: null, can_pause: true, volume: 35 },
      { id: "c2", name: "Living Room Google TV", model: "Chromecast HD", online: true, app: null, state: "idle",
        title: null, subtitle: null, art: null, can_pause: false, volume: 80 },
    ],
    people: [{ name: "James", home: true, since: start - 3 * 3600 }, { name: "Claire", home: false, since: start - 40 * 60 },
             { name: "Ed", home: true, since: start - 25 * 60 }],
    computers: [
      { name: "Home PC", on: true, busy: false, mbps: 0.4, ip: "192.168.1.20", link: "Cable",
        stats: { here: true, cpu: 12, memory: 58, disk_free_gb: 214, disk_used: 46, uptime: 3 * 86400 + 5 * 3600, temp: null } },
      { name: "Laptop", on: true, busy: true, mbps: 24.0, ip: "192.168.1.31", link: "Wi-Fi",
        stats: { cpu: 41, memory: 72, disk_free_gb: 88, disk_used: 63, uptime: 5 * 3600, temp: null } },
      { name: "Raspberry Pi", on: true, busy: false, mbps: 0.1, ip: "192.168.1.40", link: "Wi-Fi",
        stats: { cpu: 9, memory: 34, disk_free_gb: 3, disk_used: 81, uptime: 12 * 86400, temp: 51.5 } },
      { name: "Old laptop", on: false, busy: false, mbps: null, last_seen: start - 7 * 3600 },
    ],
    ring: { name: "Front Door", battery: 80, wifi: "good", motion_on: true, quiet_until: null,
            events: [[25, "motion"], [26, "press"], [90, "motion"], [160, "motion"], [300, "motion"], [470, "press"], [560, "motion"]]
              .map(([m, kind]) => ({ ts: start - m * 60, kind })) },
    ringLive: null, ringCount: 0,
    log: [],
  };

  function ringSnapshot() {
    const r = house.ring, day0 = new Date(); day0.setHours(0, 0, 0, 0);
    const today = r.events.filter(e => e.ts * 1000 >= day0).sort((a, b) => b.ts - a.ts);
    const last = k => (today.find(e => e.kind === k) || {}).ts || null;
    const live = house.ringLive && now() - house.ringLive.ts < 120 ? house.ringLive : null;
    return { name: r.name, battery: r.battery, wifi: r.wifi, motion_on: r.motion_on, last_press: last("press"),
             last_motion: last("motion"), presses: today.filter(e => e.kind === "press").length,
             motions: today.filter(e => e.kind === "motion").length, timeline: today, live, error: null,
             quiet_until: r.quiet_until && r.quiet_until > now() ? r.quiet_until : null };
  }

  // The demo's "Ring the doorbell" button
  window.demoRing = () => {
    house.ringCount += 1;
    house.ringLive = { id: house.ringCount, kind: "press", ts: now() };
    house.ring.events.push({ ts: now(), kind: "press" });
    note("Someone pressed the doorbell");
  };
  const wx = weather();

  function note(text) { house.log.unshift({ ts: now(), text, ok: true }); house.log = house.log.slice(0, 12); }

  function status() {
    return {
      ok: true, now: now(),
      alexa: {
        switches: house.switches, sensors: house.sensors, other: [], rooms: house.rooms, routines: house.routines,
        echos: house.echos.map(e => Object.assign({}, e, e.has_media ? { title: SONGS[e.song][0], subtitle: SONGS[e.song][1] } : {})),
        updated: now() - 20, error: null,
      },
      heating: { running: true, name: "Moby's Place", room: 19.6, target: 20, mode: "Schedule", boost_ends: null, outside: 7.4,
                 link: "https://github.com/cs97jjm3/mobys-heat" },
      race: { running: true, link: "https://edsf1.jmmcp.uk", port: 8080 },
      devices: { tv: house.tv, ps5: house.ps5, xbox: house.xbox },
      weather: wx,
      ring: ringSnapshot(),
      casts: house.casts,
      home: { people: house.people, computers: house.computers, error: null, updated: now() },
      log: house.log,
    };
  }

  const routes = {
    "/api/status": async () => status(),
    "/api/refresh": async () => { await wait(500); return status(); },
    "/api/login": async () => ({ ok: true }),
    "/api/switch": async b => {
      await wait(450);
      const s = house.switches.find(x => x.id === b.id);
      if (b.hue != null) { Object.assign(s, { hue: b.hue, power: "ON" }); note(`${s.name} changed colour`); }
      else if (b.kelvin != null) { Object.assign(s, { hue: null, power: "ON" }); note(`${s.name} set to ${b.kelvin < 3500 ? "warm" : "cool"} white`); }
      else if (b.brightness != null) { s.brightness = b.brightness; note(`${s.name} set to ${b.brightness}%`); }
      else { s.power = b.on ? "ON" : "OFF"; note(`${s.name} turned ${b.on ? "on" : "off"}`); }
      return status();
    },
    "/api/routine": async b => {
      await wait(700);
      const lights = { "Goodnight": "OFF", "Leaving the house": "OFF", "Good morning": "ON", "Sunset lights": "ON" }[b.name];
      if (lights) house.switches.filter(s => s.label === "Light" && s.reachable).forEach(s => s.power = lights);
      if (b.name === "Film night") {
        house.switches.forEach(s => { if (s.label === "Light" && s.reachable) s.power = s.name === "Lounge lamp" ? "ON" : "OFF"; });
        house.switches[0].brightness = 20; house.tv.state = "on";
      }
      note(`Ran ${b.name}`);
      return status();
    },
    "/api/tv": async b => {
      await wait(b.action === "power_on" ? 1200 : 400);
      const tv = house.tv;
      const words = { power_on: "Turned the TV on", power_off: "Turned the TV off", volume_up: "TV volume up",
                      volume_down: "TV volume down", mute: "TV muted", app: `Opened ${b.app_name || "an app"} on the TV` };
      if (b.action === "power_on") tv.state = "on";
      if (b.action === "app") tv.watching = b.app_name;
      if (b.action === "power_off") tv.state = "standby";
      note(words[b.action] || "TV");
      return status();
    },
    "/api/ring/live": async () => ({ ok: true, live: house.ringLive }),
    "/api/ring": async b => {
      await wait(400);
      if (b.action === "motion_on" || b.action === "motion_off") {
        house.ring.motion_on = b.action === "motion_on"; note(`Doorbell motion alerts ${house.ring.motion_on ? "on" : "off"}`);
      }
      if (b.action === "quiet_on") { house.ring.quiet_until = now() + 3600; note("Quiet hour started: Echos on Do Not Disturb"); }
      if (b.action === "quiet_off") { house.ring.quiet_until = null; note("Quiet hour ended"); }
      return status();
    },
    "/api/cast": async b => {
      await wait(300);
      const c = house.casts.find(x => x.id === b.id);
      if (b.action === "pause") c.state = "paused";
      if (b.action === "play") c.state = "playing";
      if (b.action === "volume") c.volume = b.value;
      if (b.action === "stop") { Object.assign(c, { app: null, state: "idle", title: null, subtitle: null }); note(`${c.name}: stopped casting`); }
      return status();
    },
    "/api/echo": async b => {
      await wait(300);
      const e = house.echos.find(x => x.serial === b.serial);
      if (b.action === "play") e.playing = true;
      if (b.action === "pause") e.playing = false;
      if (b.action === "next") { e.song = (e.song + 1) % SONGS.length; e.playing = true; }
      if (b.action === "previous") { e.song = (e.song + SONGS.length - 1) % SONGS.length; e.playing = true; }
      if (b.action === "volume") e.volume = b.value;
      if (b.action === "dnd") { e.dnd = b.value; note(`${e.name}: Do Not Disturb ${b.value ? "on" : "off"}`); }
      return status();
    },
  };

  // Every 45 seconds the front door camera spots someone (or stops), so the motion tile changes
  setInterval(() => {
    const door = house.sensors[0];
    door.motion = door.motion === "DETECTED" ? "NOT_DETECTED" : "DETECTED";
    door.motion_changed = now();
  }, 45000);

  // ---------- a pretend live view: a little animated front door, drawn in the browser ----------
  function frontDoorScene(canvas) {
    const g = canvas.getContext("2d"), W = canvas.width, H = canvas.height;
    let t = 0;
    return () => {
      t += 1 / 15;
      const sky = g.createLinearGradient(0, 0, 0, H);
      sky.addColorStop(0, "#1d2a44"); sky.addColorStop(1, "#3c3550");
      g.fillStyle = sky; g.fillRect(0, 0, W, H);
      g.fillStyle = "#6b5b52"; g.fillRect(0, H * 0.08, W, H * 0.72);                          // brick wall
      g.strokeStyle = "rgba(0,0,0,.18)"; g.lineWidth = 2;
      for (let y = H * 0.08; y < H * 0.8; y += 26) {
        g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke();
        for (let x = (y / 26) % 2 ? 0 : 40; x < W; x += 80) { g.beginPath(); g.moveTo(x, y); g.lineTo(x, y + 26); g.stroke(); }
      }
      const glow = 0.85 + Math.sin(t * 3) * 0.04;                                              // porch light
      const lamp = g.createRadialGradient(W * 0.68, H * 0.2, 5, W * 0.68, H * 0.2, W * 0.45);
      lamp.addColorStop(0, `rgba(255,200,120,${0.55 * glow})`); lamp.addColorStop(1, "rgba(255,200,120,0)");
      g.fillStyle = lamp; g.fillRect(0, 0, W, H);
      g.fillStyle = "#ffd88a"; g.beginPath(); g.arc(W * 0.68, H * 0.2, 14, 0, Math.PI * 2); g.fill();
      g.fillStyle = "#3a2a24"; g.fillRect(W * 0.38, H * 0.18, W * 0.24, H * 0.62);             // door frame
      g.fillStyle = "#7d1f2b"; g.fillRect(W * 0.4, H * 0.21, W * 0.2, H * 0.59);               // red door
      g.fillStyle = "#e7c46a"; g.beginPath(); g.arc(W * 0.575, H * 0.52, 7, 0, Math.PI * 2); g.fill();
      g.font = `bold ${H * 0.06}px sans-serif`; g.fillText("12", W * 0.485, H * 0.32);
      g.fillStyle = "#8a8f96"; g.fillRect(0, H * 0.8, W, H * 0.2);                             // path
      g.fillStyle = "#b0814f"; g.fillRect(W * 0.66, H * 0.7, W * 0.11, H * 0.12);              // a parcel
      g.fillStyle = "#d9b98a"; g.fillRect(W * 0.66, H * 0.75, W * 0.11, H * 0.02);
      const sway = Math.sin(t * 1.4) * 10;                                                     // a plant in the breeze
      g.fillStyle = "#4a3b33"; g.fillRect(W * 0.18, H * 0.7, W * 0.07, H * 0.12);
      g.fillStyle = "#3f7d4b";
      for (let i = -2; i <= 2; i++) {
        g.beginPath(); g.ellipse(W * 0.215 + i * 14 + sway * (1 + Math.abs(i) * 0.3), H * 0.62, 12, 46, i * 0.35 + sway / 60, 0, Math.PI * 2); g.fill();
      }
      g.fillStyle = "rgba(0,0,0,.45)"; g.fillRect(0, 0, W, 40);                                // camera caption
      g.fillStyle = "#fff"; g.font = "20px sans-serif";
      g.fillText(`Front Door   ${new Date().toLocaleString("en-GB")}   (demo)`, 16, 27);
    };
  }

  window.addEventListener("load", () => {
    window.openLiveView = () => {
      closeLiveView();
      const box = document.createElement("div");
      box.id = "liveview";
      box.innerHTML = `<div class="lv-card" role="dialog" aria-label="Front door live view">
        <div class="lv-head"><span class="lv-badge"><i></i>LIVE</span><b>Front Door</b>
          <span class="lv-left" id="lv-left"></span><button class="lv-x" onclick="closeLiveView()" aria-label="Close">✕</button></div>
        <div class="lv-video"><video id="lv-video" autoplay playsinline muted></video><div class="lv-msg" id="lv-msg">Waking the doorbell…</div></div>
        <div class="lv-foot"><button onclick="lvSound(this)">${ICONS.speaker} Sound on</button>
          <button onclick="lvPicture()">${ICONS.camera} Take picture</button><span id="lv-shot"></span></div></div>`;
      box.addEventListener("click", e => { if (e.target === box) closeLiveView(); });
      document.body.appendChild(box);
      const canvas = document.createElement("canvas"); canvas.width = 1280; canvas.height = 720;
      const draw = frontDoorScene(canvas); draw();
      lv.draw = setInterval(draw, 1000 / 15);
      setTimeout(() => {
        const v = document.getElementById("lv-video");
        if (!v) return;
        v.srcObject = canvas.captureStream ? canvas.captureStream(15) : null;
        lvSay("");
      }, 1200);
      lv.ends = Date.now() + 120000;
      lv.tick = setInterval(() => {
        const left = Math.max(0, Math.round((lv.ends - Date.now()) / 1000));
        const el = document.getElementById("lv-left");
        if (el) el.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")} left`;
        if (!left) closeLiveView();
      }, 1000);
    };
    const realClose = window.closeLiveView;
    window.closeLiveView = () => { clearInterval(lv.draw); realClose(); };
  });

  const realFetch = window.fetch.bind(window);
  window.fetch = async function (url, opts) {
    const path = typeof url === "string" ? url : url.url;
    const route = routes[path];
    if (!route) return realFetch(url, opts);
    const body = opts && opts.body ? JSON.parse(opts.body) : {};
    const data = await route(body);
    return new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
  };
})();
