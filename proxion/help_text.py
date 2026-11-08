"""Words shown inside the app: welcome, Help tab steps and the ? buttons."""

GUIDE_URL = "https://github.com/ajithjoseph/proxion/blob/main/docs/USER_GUIDE.md"

WELCOME = """Welcome to Proxion!

Proxion swaps Roblox textures, sounds, meshes and fonts on your own PC. Only you see the changes.

New here? The Help tab walks you through it step by step, with buttons for each step. It takes about two minutes.

Tip: you can open configs made for Fleasion too."""

# (title, explanation, [(button label, action name), ...]) for the Help tab
STEPS = [
    (
        "Close Roblox",
        "Close Roblox completely before setting up, so its files aren't locked.",
        [],
    ),
    (
        "Install the certificate (once)",
        "Lets Roblox accept the files Proxion gives it. It only changes Roblox's own folder, not Windows. "
        "Roblox updates make a new folder, so Proxion does this again every time you press Start.",
        [("Install certificate", "install_cert")],
    ),
    (
        "Start the proxy",
        "Windows may ask for admin permission the first time. Click Yes. The dot at the top turns green. "
        "Proxion also clears Roblox's cache when it starts (you can turn that off in Setup & tools).",
        [("Start proxy", "start")],
    ),
    (
        "Add replacements",
        "Open a config someone shared (Fleasion configs work too), or make your own rule on the Replacer tab. "
        "Turn configs on with the Enabled menu. Scraped games has ready-made asset lists for popular games.",
        [("Import config…", "import"), ("Go to Replacer", "replacer"), ("Scraped games…", "scraped")],
    ),
    (
        "Play",
        "Open Roblox and join your game. Everything the game loads shows up in the Asset log, so you can find "
        "IDs to replace: right-click an asset and choose Replace.",
        [("Open Asset log", "log")],
    ),
    (
        "Changed something?",
        "Roblox keeps assets it already downloaded. After changing rules, leave the game, clear the cache "
        "and join again.",
        [("Clear cache", "clear_cache")],
    ),
]

TROUBLESHOOTING = [
    (
        "Nothing changes in game",
        "Check the proxy is running (green dot) and your config is ticked in the Enabled menu. Then close "
        "Roblox, clear the cache and rejoin.",
    ),
    (
        "The Asset log stays empty",
        "Roblox isn't going through Proxion. Stop and start the proxy, accept the admin prompt, then open "
        "Roblox after the proxy is running. Fleasion's developers say Roblox has patched this method, so it "
        "may not work at all right now.",
    ),
    (
        "Roblox can't connect",
        "Install the certificate again and restart Roblox. If it still fails, stop the proxy to play normally.",
    ),
    (
        "Back to normal",
        "Stop the proxy, then use Remove certificate in Setup & tools.",
    ),
]

KEYBINDS = """Keybinds
  Ctrl+Z   Undo last change
  Ctrl+Y   Redo last change
  Ctrl+A   Select all profiles
  Delete   Delete selected profiles
  Enter    Add the profile in the boxes below

Tips
  • Right-click a profile to enable, disable, rename, group or delete it.
  • Drag profiles to reorder them, or drop them on a group to move them in.
  • Replace With works out the type for you: an asset ID, an https:// link, a file
    (or Browse…), or leave it empty to remove the asset.
  • Asset IDs can also be type names like Hat or Decal to hit every asset of that type.
  • Load Selected copies a profile into the boxes so you can edit it, then Update Selected."""

LOG_HELP = """Asset log

Every asset Roblox loads while the proxy runs shows up here, newest first.

  • Filter by text or pick a type to narrow it down.
  • Right-click → Replace adds the IDs to the Replacer's Asset IDs box.
  • Right-click → Replace with puts the ID in Replace With (use another game's asset).
  • Action shows what Proxion did: none, id, local, cdn or remove."""

SETUP_HELP = """Setup & tools

Capture mode
  • Local capture (recommended) grabs only Roblox's traffic.
  • Regular proxy listens on this PC only. You point traffic at it yourself.

Roblox
  • Install certificate lets Roblox accept Proxion's files. Remove certificate undoes it.
  • Clear Roblox cache makes Roblox download assets again so your swaps show up.

Proxy output shows messages from the proxy engine, useful when something goes wrong."""
