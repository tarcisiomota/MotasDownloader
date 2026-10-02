"""Portable bootstrap shared by GUI and console worker."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
DATA = ROOT / 'Dados'
for sub in ('', 'Temp', 'AppData', 'LocalAppData', 'Cache', 'Config', 'Deno'):
    (DATA / sub).mkdir(parents=True, exist_ok=True)
(ROOT / 'Downloads').mkdir(exist_ok=True)
for key, value in {
    'HOME': DATA, 'USERPROFILE': DATA,
    'APPDATA': DATA / 'AppData', 'LOCALAPPDATA': DATA / 'LocalAppData',
    'XDG_CACHE_HOME': DATA / 'Cache', 'XDG_CONFIG_HOME': DATA / 'Config',
    'TEMP': DATA / 'Temp', 'TMP': DATA / 'Temp', 'DENO_DIR': DATA / 'Deno',
}.items():
    os.environ[key] = str(value)
os.environ['PATH'] = str(ROOT / 'bin') + os.pathsep + os.environ.get('PATH', '')
tempfile.tempdir = str(DATA / 'Temp')

def main():
    if '--self-test-tags' in sys.argv:
        from metadata_diagnostic import run
        run(ROOT)
        return
    if '--spotdl-worker' in sys.argv:
        sys.argv.remove('--spotdl-worker')
        from spotdl.console.entry_point import console_entry_point
        console_entry_point()
        return
    import app
    app.DOWNLOADS_FOLDER = str(ROOT / 'Downloads')
    app._bin_dir = lambda: str(ROOT / 'bin')
    app.get_spotdl_path = lambda: (
        [str(ROOT / 'SpotDL-worker.exe'), '--spotdl-worker']
        if getattr(sys, 'frozen', False) else
        [sys.executable, str(ROOT / 'portable_main.py'), '--spotdl-worker'])
    if '--self-test' in sys.argv:
        import json
        import subprocess
        import importlib.metadata
        import yt_dlp_ejs
        from spotdl.console.entry_point import console_entry_point
        gui = app.DownloaderApp()
        gui.withdraw()
        gui.update()
        assert len(gui.tabview._tab_dict) == 3
        gui._toggle_theme()
        gui._toggle_theme()
        assert app.has_ffmpeg()
        gui.destroy()
        versions = {name: importlib.metadata.version(name) for name in ['yt-dlp', 'spotdl', 'customtkinter']}
        for name in ('ffmpeg', 'ffprobe', 'deno'):
            flag = '--version' if name == 'deno' else '-version'
            result = subprocess.run([str(ROOT / 'bin' / (name + '.exe')), flag], capture_output=True, text=True, check=True)
            versions[name] = result.stdout.splitlines()[0]
        print(json.dumps({'ok': True, 'root': str(ROOT), 'versions': versions}, ensure_ascii=False))
        return
    gui = app.DownloaderApp()
    gui.title("Mota's Downloader — Portátil v4.3")
    gui.mainloop()

if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        (DATA / 'erro-inicializacao.log').write_text(traceback.format_exc(), encoding='utf-8')
        raise
