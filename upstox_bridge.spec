# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for Upstox Trading Bridge Desktop Software."""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
project_root = Path.cwd()

# 1. Collect CustomTkinter theme and font assets
ctk_datas = collect_data_files("customtkinter")

# 2. Project asset files to bundle
datas = [
    ("config", "config"),
    ("templates", "templates"),
    ("scripts", "scripts"),
    ("watchlist.txt", "."),
]

# Include default workbooks if present
for wb_name in ("bst.xlsx", "trial.xlsx"):
    wb_file = project_root / wb_name
    if wb_file.exists():
        datas.append((wb_name, "."))

datas += ctk_datas

# 3. Explicit hidden imports to prevent missing dynamic dependencies
hiddenimports = [
    "customtkinter",
    "pystray",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "xlwings",
    "openpyxl",
    "requests",
    "yaml",
    "websockets",
    "protobuf",
    "dotenv",
    "psutil",
]

if sys.platform == "win32":
    hiddenimports += [
        "win32com",
        "win32com.client",
        "pythoncom",
        "pystray._win32",
    ]
elif sys.platform == "darwin":
    hiddenimports += [
        "pystray._darwin",
        "AppKit",
        "Cocoa",
        "Quartz",
    ]

a = Analysis(
    ["main.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest.test"],
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
    name="UpstoxBridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Launch as a clean windowed Desktop App without black terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="UpstoxBridge",
)
