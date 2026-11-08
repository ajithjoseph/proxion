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

Only `assetdelivery.roblox.com` is decrypted. Logins, cookies and every other Roblox
connection go straight through without Proxion seeing them.

## Getting Proxion.exe

Proxion builds into one `Proxion.exe`, no Python needed to run it. Two ways to get it:

* **GitHub Releases:** download `Proxion.exe` and `Proxion.exe.sha256` from the Releases page.
  Every build also shows up under the *Actions* tab as an artifact. The workflow
  (`.github/workflows/build.yml`) lints, tests, builds and smoke tests the exe on Windows.
  Pushing a tag like `v0.2.0` publishes a Release.
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

## Security

Proxion is a man-in-the-middle proxy, so it's built to keep that power small:

* **Only asset traffic is intercepted.** mitmproxy runs with `allow_hosts` set to
  `assetdelivery.roblox.com`. Everything else Roblox sends passes through untouched.
* **Nothing on your network can use it.** Local capture mode has no network port at all.
  Regular mode listens on `127.0.0.1` only.
* **The certificate is only trusted by Roblox.** It's added to Roblox's own `cacert.pem`, never
  to Windows. The private key stays in `%APPDATA%\Proxion\certs`. Use **Remove certificate**
  to undo it. Note that a Roblox install under Program Files is shared by every Windows user
  on the PC, so they would trust your certificate too.
* **Configs from other people are checked.**
  * Network paths (`\\server\share`), device paths, environment variables and Windows
    device names are refused, because opening a network path makes Windows send your login
    hash to that server.
  * Download links must be `https://` and can't point at your own PC, a bare IP or your LAN.
  * Before a config that uses files outside the configs folder, or downloads from the web,
    gets turned on, Proxion shows you exactly what it touches and asks first.
  * Oversized (over 20 MB) and absurdly nested files are rejected, and broken entries are
    skipped instead of crashing the app.
* **Local files are served under random links** over HTTPS GET only, never by asset ID, and
  only regular files under 200 MB.
* **Logs can't fill your disk.** The asset log rotates at 5 MB and the window keeps the last
  5,000 assets.
* **Builds are reproducible and traceable.** CI installs exact versions with hash checking
  (`requirements-build.lock`), pins every GitHub Action to a commit, runs with a read-only
  token, and publishes a SHA-256 checksum plus a signed build provenance attestation. Check a
  download with:

  ```
  gh attestation verify Proxion.exe --repo ajithjoseph/proxion
  ```

Found a security problem? Please open a private security advisory on GitHub rather than a
public issue.

## Development

```
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
ruff check . && ruff format --check .
pytest
```

The build dependencies are locked with hashes. After changing `requirements-build.in`, update the lock:

```
uv pip compile requirements-build.in --universal --python-version 3.12 --generate-hashes -o requirements-build.lock
```
