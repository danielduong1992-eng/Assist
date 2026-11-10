# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a single easy-to-run Assist.exe."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

tzdata_datas, tzdata_binaries, tzdata_hidden = collect_all("tzdata")
assist_hidden = collect_submodules("assist")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=tzdata_binaries,
    datas=tzdata_datas,
    hiddenimports=list(set(tzdata_hidden + assist_hidden + ["tzdata", "zoneinfo"])),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Assist",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # avoid extra SmartScreen / AV false positives
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed app — double-click to run
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
