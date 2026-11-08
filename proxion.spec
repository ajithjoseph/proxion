# PyInstaller spec: builds a single Proxion.exe
# Build with:  pyinstaller proxion.spec
from PyInstaller.utils.hooks import collect_all

datas = [("proxion/addon.py", "proxion")]
binaries = []
hiddenimports = ["proxion.addon", "proxion.gui"]
for pkg in ("mitmproxy", "mitmproxy_rs", "mitmproxy_windows"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue  # mitmproxy_windows only exists on Windows
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["proxion_entry.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="Proxion",
    console=False,  # no black console window
    upx=False,
    icon="proxion.ico",
)
