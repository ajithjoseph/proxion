# Proxion user guide

This guide walks you through everything, from getting Proxion onto your PC to swapping your
first texture. No coding knowledge needed. If you get stuck, the **Help** tab inside Proxion
has the same steps, and the **?** button on each screen explains that screen.

---

## 1. What Proxion does (in plain words)

When you play Roblox, the game downloads things like textures, sounds, meshes and fonts.
Proxion sits between Roblox and the internet on **your own PC** and can hand Roblox a
different file instead. Only you see the change. Other players see the normal game.

You tell Proxion what to swap using **configs**. A config is a list of rules like
"replace sound 12345 with this other sound". Proxion can open configs made for Fleasion.

---

## 2. What you need

* A Windows 10 or 11 PC with Roblox installed.
* About 100 MB of free space.
* Admin rights on the PC (Windows asks once, the first time you start the proxy).
* Only if you build it yourself: Python 3.12 or newer from
  [python.org](https://www.python.org/downloads/). During install, tick **"Add python.exe to PATH"**.

---

## 3. Get Proxion (pick ONE way)

### Way A: download the ready-made exe (easiest)

1. Go to the project's GitHub page, then **Releases** on the right side.
2. Under the newest release, click **Proxion.exe** to download it.
   * No release yet? Open the **Actions** tab, click the newest green "Build Proxion.exe"
     run, scroll to **Artifacts**, and download **Proxion** (it's a zip with the exe inside).
3. Put `Proxion.exe` in its own folder, for example `C:\Proxion`.
4. Double click it. If Windows shows **"Windows protected your PC"**, click
   **More info** then **Run anyway**. This shows up because the exe isn't code signed. It's normal
   for small open source apps.

### Way B: build the exe yourself

1. On the GitHub page, click the green **Code** button, then **Download ZIP**.
2. Right click the zip, choose **Extract All**, and pick a folder like `C:\Proxion-src`.
3. Open that folder and double click **`build.bat`**.
   * A black window opens. It downloads what it needs and builds the app. This takes 2 to 5
     minutes the first time.
   * When it says **"Done: dist\Proxion.exe"**, press any key.
4. Your app is in the `dist` folder: `dist\Proxion.exe`. Copy it anywhere you like.

### Way C: run straight from the source (no exe)

1. Download and extract the ZIP like in Way B.
2. Double click **`run.bat`**.
   * The first time, it sets things up (1 to 3 minutes), then the window opens.
   * After that, double clicking `run.bat` opens Proxion in a few seconds.

---

## 4. First time setup (do this once)

1. **Close Roblox** completely (check the system tray too).
2. Open Proxion.
3. Go to **Setup & tools** and click **Install certificate**.
   * This lets Roblox accept the files Proxion hands it. It only touches Roblox's own folder,
     not Windows' certificate store.
   * It should say "Certificate installed in 1 Roblox folder" (or more if you use Bloxstrap
     or Fishstrap).
4. Click **Clear Roblox cache**, so Roblox downloads assets again through Proxion.
5. Click **Start proxy** at the top right. Windows may ask for admin permission. Click **Yes**.
   The dot turns green and says **running**.

---

## 5. Swap your first asset

### Option 1: use a config someone shared

1. Click **Open config…** on the **Replacer** tab and pick the `.json` file.
   You can also drag the file onto `Proxion.exe`.
2. Proxion copies it in and turns it on. You'll see its rules in the list.
3. Make sure the proxy is running (green dot), then open Roblox and join the game.

### Option 2: make your own rule

1. Start the proxy, open Roblox and join the game you want to change.
2. Go to the **Asset log** tab. Everything the game loads shows up here with its ID and type.
   * Tip: type `Audio` or `Image` in the filter box to narrow it down.
3. Click the asset you want to change, then **Use selected as target**.
4. Back on **Replacer**, give the rule a name and choose what to replace it with:
   * **Asset ID**: another Roblox asset's ID number.
   * **File**: a file on your PC (PNG, OGG, MP3, mesh, font...). Click **…** to pick it.
   * **URL**: a direct link to a file on the web.
   * **Remove**: the asset just disappears.
5. Click **Add new**.
6. Leave the game, click **Clear cache** (or just rejoin), and join again to see the change.

---

## 6. Using configs

* **Editing** picks which config you're changing right now.
* **Enabled** lets you turn on several configs at once. They all apply together.
* **New / Duplicate / Rename / Delete** manage configs.
* **Open Configs** opens the folder where configs live
  (`%APPDATA%\Proxion\configs`). You can drop `.json` files there too.
* **Export…** saves the current config so you can share it.
* **Undo (Ctrl+Z)** takes back your last change.

---

## 7. When something doesn't work

| What you see | What to do |
|---|---|
| Nothing changes in game | Make sure the proxy is **running**, the config is **Enabled**, then **Clear cache** with Roblox closed and rejoin. |
| Asset log stays empty | Roblox isn't going through Proxion. Restart the proxy, accept the admin prompt, then start Roblox **after** the proxy. Roblox may also have blocked this method (see below). |
| Roblox says it can't connect | Click **Install certificate** again (Roblox updates make a fresh folder), restart Roblox. If it still fails, **Stop proxy** to play normally. |
| "Windows protected your PC" | Click **More info**, then **Run anyway**. |
| `build.bat` says Python isn't found | Install Python from python.org and tick **Add python.exe to PATH**, then try again. |
| Antivirus flags the exe | Apps built with PyInstaller sometimes get false alarms. Build it yourself with `build.bat` if you prefer. |

**Heads up:** Fleasion's developers say Roblox has patched the method these tools use. If
the asset log stays empty no matter what, that's probably why, and there isn't a fix on our side.

---

## 8. Going back to normal / uninstalling

1. Click **Stop proxy**.
2. In **Setup & tools**, click **Remove certificate**.
3. Delete `Proxion.exe` (or the source folder).
4. Optional: delete `%APPDATA%\Proxion` to remove your configs and settings.

---

## 9. Play fair

Use Proxion for cosmetic changes. Using it to get an edge (like removing walls or bushes) can
get you banned from that game, and changing the client goes against Roblox's Terms of Use.
Only open configs from people you trust, and Proxion will warn you if a config points at files
outside its own folder or at non-https links.
