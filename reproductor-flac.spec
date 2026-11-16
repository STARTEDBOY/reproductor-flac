# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec para Reproductor FLAC (Windows/Linux)."""

from pathlib import Path

block_cipher = None
base = Path(SPECPATH)

_datas = [(str(base / "assets"), "assets")]
if (base / "mpv").exists():
    _datas.append((str(base / "mpv"), "mpv"))

a = Analysis(
    [str(base / "main.py")],
    pathex=[str(base)],
    binaries=[],
    datas=_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="ReproductorFLAC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(base / "assets" / "icon.png"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ReproductorFLAC",
)
