# Proxion

A Roblox asset replacer. Proxion runs a small proxy on your PC that sits between the Roblox
client and Roblox's asset servers, so you can swap textures, sounds, meshes and animations
for other ones, for your own files, or remove them. Changes only show up on **your** screen.

## How it works

1. Roblox asks `assetdelivery.roblox.com/v1/assets/batch` where to download each asset.
2. Proxion catches that request (using [mitmproxy](https://mitmproxy.org)) and:
   * **Asset ID** rules: changes the requested ID, so Roblox downloads the replacement instead.
   * **Local file** rules: points Roblox at a link Proxion answers itself with your file.
   * **Remove** rules: tells Roblox the asset doesn't exist.
3. Every asset Roblox loads is listed in the **Asset log** tab, so you can find IDs to replace.

Roblox only trusts its own certificate list (`ssl/cacert.pem` inside each version folder), so
Proxion adds its certificate there. Bloxstrap and Fishstrap installs are handled too.

## Quick start (Windows)

1. Install Python 3.11 or newer from python.org (tick "Add to PATH").
2. Double click `run.bat`. The first run installs mitmproxy.
3. Add a rule in **Replacements**.
4. Close Roblox, press **Clear Roblox cache** in *Setup & tools*, then **Start proxy**.
5. Open Roblox and join a game.

The first time you start the proxy in local capture mode, Windows may ask to allow a
driver (WinDivert, used by mitmproxy to capture only Roblox's traffic). Say yes, and run
Proxion as admin if it fails to start.

## Command line

```
python -m proxion               # window
python -m proxion run           # proxy only, in the terminal
python -m proxion install-cert
python -m proxion uninstall-cert
python -m proxion clear-cache
```

## Notes

* Rules save to `%APPDATA%\Proxion\config.json` and apply live while the proxy runs. Roblox
  caches assets, so clear the cache or rejoin to see changes.
* Roblox updates create a fresh version folder. Proxion re-adds its certificate each time
  you press Start.
* Use it for cosmetic stuff. Using swaps to get an edge in a game (like removing walls or
  foliage) can get you banned by that game, and editing the client is against the Roblox
  Terms of Use, so it's at your own risk.

## Tests

```
pip install -e .[dev]
pytest
```
