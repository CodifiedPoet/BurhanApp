# -*- mode: python ; coding: utf-8 -*-
import sys

is_mac = sys.platform == 'darwin'

a = Analysis(
    ['run_qt.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'scanmaker',
        'scanmaker.qt_app',
        'scanmaker.qt_canvas',
        'scanmaker.models',
        'scanmaker.rendering',
        'scanmaker.utils',
        'scanmaker.theme',
        'scanmaker.updater',
    ],
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
    [],
    exclude_binaries=True,
    name='BurhanApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/BurhanApp.icns' if is_mac else 'assets/BurhanApp.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BurhanApp',
)

if is_mac:
    app = BUNDLE(
        coll,
        name='BurhanApp.app',
        icon='assets/BurhanApp.icns',
        bundle_identifier='com.burhanapp.scanmaker',
        info_plist={
            'CFBundleShortVersionString': '2.0.0',
            'CFBundleName': 'BurhanApp',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.15',
        },
    )
