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

## Getting Proxion.exe

Proxion builds into one `Proxion.exe`, no Python needed to run it. Two ways to get it:

* **GitHub (no setup):** push this folder to a GitHub repo. The workflow in
  `.github/workflows/build.yml` builds the exe on Windows, tests it, and puts it under the
  run's *Artifacts*. Push a tag like `v0.1.0` and it also attaches the exe to a Release.
* **Your own PC:** install Python 3.12+ from python.org, then double click `build.bat`.
  The exe lands in `dist\Proxion.exe`.

Windows SmartScreen may warn the first time because the exe isn't code signed. Click
*More info* then *Run anyway*.

## Quick start

1. Open `Proxion.exe` (or `run.bat` if you're running from source).
2. Add a rule in **Replacements**.
4. Close Roblox, press **Clear Roblox cache** in *Setup & tools*, then **Start proxy**.
5. Open Roblox and join a game.

The first time you start the proxy in local capture mode, Windows may ask to allow a
driver (WinDivert, used by mitmproxy to capture only Roblox's traffic). Say yes, and run
Proxion as admin if it fails to start.

## Configs (works with Fleasion configs)

Rules live in **configs**: one `.json` file each, in `%APPDATA%\Proxion\configs`. They use
the same format as Fleasion, so you can open a Fleasion config in Proxion and the other way round.

* **Open config…** copies a config file into Proxion and turns it on. You can pick several at once.
* You can also **drag a config onto Proxion.exe**, or set Proxion as the app that opens `.json` files.
* The **Config** dropdown picks which config you're editing. **Turned on** decides whether the
  proxy uses it. Any number of configs can be on at once. If two hit the same asset, the one
  listed later wins.
* **New / Duplicate / Rename / Delete / Export… / Folder** do what they say.
* Rules can be put in groups. Turning a group off turns off everything in it.

What a config looks like:

```json
{
  "replacement_rules": [
    {"name": "Sky", "replace_ids": [600830446, 600831635], "mode": "id", "with_id": 1234567, "enabled": true},
    {"name": "My texture", "replace_ids": [111111111], "mode": "local", "local_path": "/MyFolder/tex.png"},
    {"name": "From the web", "replace_ids": [222222222], "mode": "cdn", "cdn_url": "https://example.com/a.png"},
    {"name": "No hats", "replace_ids": ["Hat"], "mode": "remove"},
    {"type": "group", "name": "Skyboxes", "children": []}
  ]
}
```

* `replace_ids`: asset IDs, or a type name like `Hat`, `Decal`, `Mesh` to hit every asset of
  that type. A type can be removed, or replaced with a file or URL, but not swapped to one ID.
* `local_path` starting with `/` is relative to the configs folder, like in Fleasion, so a
  config can ship with its files in a subfolder.
* Fleasion's TexturePack slot keys (like `"123:1"`) and `R15Animation` style selectors aren't
  supported yet. Proxion keeps them in the file and tells you how many it skipped.

## Command line

```
python -m proxion               # window
python -m proxion open my.json  # open configs in the window
python -m proxion run           # proxy only, in the terminal
python -m proxion install-cert
python -m proxion uninstall-cert
python -m proxion clear-cache
```

## Notes

* Config changes apply live while the proxy runs. Roblox caches assets, so clear the cache or
  rejoin to see changes.
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
