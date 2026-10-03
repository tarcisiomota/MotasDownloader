from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata
from pathlib import Path

datas, binaries, hiddenimports = [], [], []
for package in ('customtkinter', 'yt_dlp', 'yt_dlp_ejs', 'spotdl', 'pykakasi', 'rapidfuzz', 'vlc',
                'moviepy', 'pydub'):
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden
for distribution in ('yt-dlp', 'spotdl', 'customtkinter'):
    datas += copy_metadata(distribution, recursive=True)
datas += collect_data_files('ytmusicapi')
a = Analysis(['portable_main.py'], pathex=[SPECPATH], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports, hookspath=[str(Path(SPECPATH) / 'hooks')],
             runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MotasDownloader',
          debug=False, strip=False, upx=False, console=False)
worker = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SpotDL-worker',
             debug=False, strip=False, upx=False, console=True)
coll = COLLECT(gui, worker, a.binaries, a.datas, strip=False, upx=False,
               name='MotasDownloader-Portable')
