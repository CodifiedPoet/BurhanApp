# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for BurhanApp."""

import os
import sys
import customtkinter

block_cipher = None

ctk_path = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ['run.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        (ctk_path, 'customtkinter'),
    ],
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL._tkinter_finder',
        'fitz',
        'tkinter',
        'tkinter.filedialog',
        'tkinter.colorchooser',
        'tkinter.simpledialog',
        'tkinter.messagebox',
    ],
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
    name='BurhanApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # No console window — GUI app
    icon='assets/BurhanApp.icns' if sys.platform == 'darwin' else 'assets/BurhanApp.ico',
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
    name='BurhanApp',
)
