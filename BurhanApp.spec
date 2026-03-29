# -*- mode: python ; coding: utf-8 -*-

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
    icon='assets/BurhanApp.ico',
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
