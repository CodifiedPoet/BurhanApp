# -*- mode: python ; coding: utf-8 -*-
import sys
import os

is_mac = sys.platform == 'darwin'

_spec_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(_spec_dir, 'run_qt.py')],
    pathex=[os.path.join(_spec_dir, 'src')],
    binaries=[],
    datas=[
        (os.path.join(_spec_dir, 'assets'), 'assets'),
        (os.path.join(_spec_dir, 'src', 'scanmaker'), 'scanmaker'),
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
