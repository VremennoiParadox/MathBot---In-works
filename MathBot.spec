# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — macOS console .app (MathBot Phase 5)

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    binaries=[],
    datas=[
        ("prompts", "prompts"),
        ("assets", "assets"),
        ("assets/templates", "assets/templates"),
        ("config.json.default", "."),
        ("templates/README.md", "templates"),
    ],
    hiddenimports=[
        "pynput.keyboard",
        "pynput.mouse",
        "cv2",
        "imagehash",
        "PIL._imaging",
        "sqlite3",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MathBot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.icns" if (root / "assets" / "icon.icns").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MathBot",
)

app = BUNDLE(
    coll,
    name="MathBot.app",
    icon="assets/icon.icns" if (root / "assets" / "icon.icns").exists() else None,
    bundle_identifier="com.mathbot.app",
)
