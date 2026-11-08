import argparse
import os
import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "__mitmdump":
        # Used by the single exe build to run the proxy as a child process.
        from mitmproxy.tools.main import mitmdump
        mitmdump(sys.argv[2:])
        return

    files = sys.argv[1:]
    if files and all(os.path.isfile(f) for f in files):
        # Config files dragged onto Proxion.exe or opened with it.
        from .gui import main as gui_main
        gui_main(files)
        return

    p = argparse.ArgumentParser(prog="proxion", description="Roblox asset replacer")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("gui", help="open the window (default)")
    sub.add_parser("install-cert", help="trust Proxion's certificate in every Roblox install")
    sub.add_parser("uninstall-cert", help="remove Proxion's certificate from Roblox")
    op = sub.add_parser("open", help="open config files (Proxion or Fleasion) in the window")
    op.add_argument("files", nargs="+")
    sub.add_parser("clear-cache", help="delete Roblox's asset cache")
    sub.add_parser("run", help="run the proxy in this terminal without the window")
    args = p.parse_args()

    if args.cmd == "open":
        from .gui import main as gui_main
        gui_main(args.files)
        return
    if args.cmd in (None, "gui"):
        from .gui import main as gui_main
        gui_main()
        return

    from . import config, roblox
    if args.cmd == "install-cert":
        for f in roblox.install_cert():
            print("patched", f)
        if not roblox.version_dirs():
            print("No Roblox install found.")
    elif args.cmd == "uninstall-cert":
        for f in roblox.uninstall_cert():
            print("cleaned", f)
    elif args.cmd == "clear-cache":
        for f in roblox.clear_cache():
            print("removed", f)
    elif args.cmd == "run":
        import subprocess
        from .proxy import build_command
        roblox.install_cert()
        sys.exit(subprocess.call(build_command(config.load())))


if __name__ == "__main__":
    main()
