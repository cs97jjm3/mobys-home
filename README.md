# Moby's Home

A home dashboard that runs on a Windows PC and shows everything in one place. It covers the Alexa lights and plugs, the Ring doorbell (with live view), the Echos, the TV, the TV box, Chromecasts and games consoles, who's home, the computers in the house, the weather, and links to the other home dashboards. It works in a browser on the PC, on phones and tablets around the house, and from outside through a Cloudflare tunnel if you set one up.

Try the demo, running against a pretend house: https://cs97jjm3.github.io/mobys-home/

## What it shows

- **Who's home:** each person's phone being on the home Wi-Fi shows them as home. Phones nap off the Wi-Fi to save battery, so someone only shows as out after 10 minutes away.
- **Lights and plugs:** anything Alexa can switch, with dimming where the light supports it, and colour and warm-to-cool white for colour lights. A coloured light glows in its own colour on the page. The switching goes through Alexa, so there's no need for separate Tuya or Smart Life keys.
- **Routines:** your Alexa routines as buttons.
- **Echos:** whether each one is online, what's playing (with play, pause and skip), the volume, Do Not Disturb, and the next alarm or timer.
- **Weather:** now, the next few hours and the next five days, from Open-Meteo. You don't need an account.
- **TV and consoles:**
  - Samsung TV: whether it's on and which app is on screen (or your usual source, like BT TV), with power, volume and apps.
  - BT / EE TV Box Pro: says when it's on Netflix or YouTube, and when it's streaming any other app (iPlayer, ITVX, Prime and so on). Live channels show as just "BT TV". See "The EE TV box" below.
  - Chromecasts and Google TVs: found by themselves. Shows what's being cast, with the title and picture, play, pause, stop and volume.
  - PS5: on or in rest mode. It can also show which game is being played, if you link a PlayStation account.
  - Xbox: on or asleep.
- **Computers:** on, off, busy (with the speed), Wi-Fi or cable, and when each was last seen. The PC running Moby's Home shows its processor, memory, disk space and how long it's been on. Other computers can show the same by running a small helper (see below).
- **Ring doorbell:** a banner and chime on every open dashboard within seconds of someone pressing the bell, and a **live view** of the front door with sound and a Take picture button, no Ring Protect plan needed. Also today's presses and motion on a timeline, battery, motion alerts on or off, a Quiet hour button (Do Not Disturb on every Echo), and optionally a colour light that glows for 10 seconds when someone rings.
- **Other dashboards:** tiles for Moby's Heat (heating) and the race weekend dashboard. Each opens in its own window.

## The look

Four modes, picked with the switch at the top: **Auto** (follows the device's light or dark setting), **Day**, **Night** (lights that are on glow) and **Colour** (each card in its own colour). Click any card's title to fold it away. Each phone or laptop remembers its own mode and folded cards.

## Setting it up

1. Install Python 3.12 or later.
2. Install the libraries:
   ```
   py -m pip install -r requirements.txt
   ```
3. Copy `home_config.example.ini` to `home_config.ini` and fill it in. It explains each setting as you go.
4. Sign in to Alexa once:
   ```
   py alexa_peek.py
   ```
   It asks for your Amazon email, password and the code Amazon sends you. The sign-in is then remembered in `alexa_login.json`.
5. Start it with `start_home.bat`. If the dashboard ever stops, the batch file starts it again after 30 seconds.
6. Open http://localhost:8095 in a browser.

To start it automatically, add `start_home.bat` to Task Scheduler with the trigger "When I log on".

## Showing the PS5 game (optional)

1. Sign in at playstation.com in a browser.
2. In the same browser, go to https://ca.account.sony.com/api/v1/ssocookie
3. Copy the long code shown after `npsso`.
4. Put it in `home_config.ini` under `[playstation]`.

The code lasts about two months. The dashboard warns you a week before it runs out. This uses an unofficial library, so the dashboard only checks every couple of minutes.

## Who's home and the computers

These come from the BT Smart Hub's device list, which the hub shares with the home network without a password. Run `py hub_devices.py` to list every device with its MAC address, then add the ones you want to `home_config.ini`:

```
[people]
James = aa:bb:cc:dd:ee:ff

[computers]
Laptop = aa:bb:cc:dd:ee:ff
```

To show processor, memory and disk for another computer, run the helper on it. It only shares those figures and can't change anything.

- **Windows:** copy `moby_agent.py` and `start_moby_agent.bat` to it and run the batch file (add it to Task Scheduler to start it at log on). Allow it on private networks if Windows asks.
- **Raspberry Pi:** copy `moby_agent.py` over, then `python3 moby_agent.py`. Add `@reboot python3 /home/pi/moby_agent.py` to `crontab -e` to start it at boot. The Pi also shows its temperature.

It's best not to run it on a work laptop: company IT rules usually don't allow personal software on work machines.

## The EE TV box

The BT / EE TV Box Pro has no public way to ask what's on, but two things work:

- It answers the DIAL questions phone apps use to find it (port 56789). Only Netflix and YouTube register there, so it can say when either is running. Everything else, including live TV, shows as "stopped".
- The BT Smart Hub's device list counts the data each device uses. When the box is pulling more than 1.5 Mbit/s it's streaming; live channels from the aerial are close to 0.

Set `tv_box` (its address) and `tv_box_mac` (its MAC address) under `[devices]`. The scripts `bt_box_probe.py`, `bt_box_apps.py`, `bt_box_hunt.py` and `hub_rate_test.py` are the tests used to work this out.

## The Ring doorbell

Sign in once with `py ring_test.py`. It asks for your Ring email, password and the code Ring sends you, then saves `ring_token.json` (keep it private; it's kept off GitHub). Add `py ring_test.py listen` to check live presses come through. To light up a colour light when someone rings, set `flash_light` under `[ring]` in `home_config.ini`.

**Live view:** tap Live view on the Front Door card (or on the doorbell banner). The video goes straight from Ring to your browser; Moby's Home only passes the set-up messages between them, so it works at home and through your own web address. It closes itself after 2 minutes to save the doorbell's battery. Take picture saves a still from the live video.

Without a Ring Protect plan, a battery doorbell can't take pictures on demand and there are no recordings, so the dashboard's pictures come from live view only. The live video part of the Ring library is marked experimental.

## Samsung TV

The first time the dashboard sends the TV a button press, the TV asks whether to allow it. Say yes with the TV remote. After that, the permission is remembered in `samsung_token.txt`. The connection is kept open between presses, so buttons respond quickly, and it closes after 10 minutes unused.

Which app is on screen comes from a quieter check that never makes the TV ask anything. If someone pressed Deny by mistake, go to the TV's Settings > General > External Device Manager > Device Connection Manager > Device List and set Moby's Home to Allow.

## Colour lights

Colour and white work for any Alexa light that supports them. `py colour_test.py` lists which lights can do colour, and `py colour_test.py "Light name"` tries each way of asking Alexa on that light, which is how this was worked out.

## Checking it's all working

`py check_home.py` checks the settings, the files, the other dashboards and each device, and tells you what isn't answering. `py ps5_test.py` is a closer check for the PS5 if it shows as off when it's on.

To run the tests:
```
py -m pytest tests
```

## Keep these private

These files hold passwords, PINs or sign-ins. The `.gitignore` keeps them off GitHub, so never force them in:

- `home_config.ini`
- `home_secret.txt`
- `alexa_login.json`
- `psn_token.json`
- `samsung_token.txt`
- `ring_token.json` and `ring_listen.json`
