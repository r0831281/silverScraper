# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['scraper.py'],
    pathex=[],
    binaries=[],
    datas=[('proxy/server.js', 'proxy'), ('proxy/node_modules', 'proxy/node_modules')],
        hiddenimports=[
        'bs4',
        'requests',
        'pandas',
        'tkinter',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='scraper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
