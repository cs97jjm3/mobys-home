# Moby's Home

A home dashboard that runs on a Windows PC and shows everything in one place. It covers the Alexa lights and plugs, the Echos, the TV and games consoles, the weather, and links to the other home dashboards. It works in a browser on the PC, on phones and tablets around the house, and from outside through a Cloudflare tunnel if you set one up.

## What it shows

- **Lights and plugs:** anything Alexa can switch, with dimming where the light supports it. The switching goes through Alexa, so there's no need for separate Tuya or Smart Life keys.
- **Routines:** your Alexa routines as buttons.
- **Echos:** whether each one is online, what's playing (with play, pause and skip), the volume, Do Not Disturb, and the next alarm or timer.
- **Weather:** now, the next few hours and the next five days, from Open-Meteo. You don't need an account.
- **TV and consoles:**
  - Samsung TV: whether it's on, with power, volume and apps.
  - PS5: on or in rest mode. It can also show which game is being played, if you link a PlayStation account.
  - Xbox: on or asleep.
- **Other dashboards:** tiles for Moby's Heat (heating) and the race weekend dashboard. Each opens in its own window.

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

## Samsung TV

The first time the dashboard sends the TV a button press, the TV asks whether to allow it. Say yes with the TV remote. After that, the permission is remembered in `samsung_token.txt`.

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
