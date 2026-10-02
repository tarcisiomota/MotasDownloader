"""Prepare external tools, test and build on Windows using official releases."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent

def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'MotasDownloader-build'}), timeout=90)

def prepare_tool(repo, asset_name, wanted):
    with fetch(f'https://api.github.com/repos/{repo}/releases/latest') as response:
        release = json.load(response)
    asset = next(a for a in release['assets'] if a['name'] == asset_name)
    expected = asset.get('digest') or ''
    if not expected.startswith('sha256:'):
        raise RuntimeError('Release does not provide a SHA-256 digest: ' + asset_name)
    cache = ROOT / '.build-cache'
    cache.mkdir(exist_ok=True)
    archive = cache / asset_name
    with fetch(asset['browser_download_url']) as response, archive.open('wb') as output:
        shutil.copyfileobj(response, output)
    with archive.open('rb') as stream:
        actual = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        raise RuntimeError('Checksum mismatch: ' + asset_name)
    binary_dir = ROOT / 'bin'
    binary_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for filename in wanted:
            members = [n for n in z.namelist() if n.rsplit('/',1)[-1] == filename]
            if len(members) != 1:
                raise RuntimeError('Missing or ambiguous binary: ' + filename)
            with z.open(members[0]) as source, (binary_dir / filename).open('wb') as dest:
                shutil.copyfileobj(source,dest)
        for member in z.namelist():
            if member.rsplit('/',1)[-1].lower() in ('license.txt','license.md','license'):
                dest = ROOT / 'Licencas' / repo.replace('/','-')
                dest.mkdir(parents=True,exist_ok=True)
                (dest / member.rsplit('/',1)[-1]).write_bytes(z.read(member))
    (cache / (repo.replace('/','-') + '.json')).write_text(json.dumps({
        'repository':repo,'tag':release['tag_name'],'url':asset['browser_download_url'],
        'sha256':actual},indent=2),encoding='utf-8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--skip-download',action='store_true',help='Use tools already present in bin/')
    args = parser.parse_args()
    if sys.platform != 'win32' or sys.version_info[:2] != (3,12) or struct.calcsize('P') != 8:
        raise SystemExit('Use Python 3.12 x64 on Windows, with Tcl/Tk.')
    if not args.skip_download:
        prepare_tool('BtbN/FFmpeg-Builds','ffmpeg-master-latest-win64-lgpl.zip',('ffmpeg.exe','ffprobe.exe'))
        prepare_tool('denoland/deno','deno-x86_64-pc-windows-msvc.zip',('deno.exe',))
    for filename in ('ffmpeg.exe','ffprobe.exe','deno.exe'):
        if not (ROOT/'bin'/filename).is_file():
            raise SystemExit('Missing bin/' + filename)
    for option, required in [('-encoders', ('libopenh264', 'aac')), ('-filters', ('subtitles', 'ass'))]:
        result = subprocess.run([str(ROOT/'bin'/'ffmpeg.exe'), '-hide_banner', option],
            capture_output=True, text=True, check=True)
        if any(name not in result.stdout for name in required):
            raise SystemExit('FFmpeg lacks required features: ' + ', '.join(required))
    if args.prepare_only:
        return
    subprocess.run([sys.executable,'-m','unittest','discover','-s','.',
                    '-p','test_*.py','-v'],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','portable.spec'],cwd=ROOT,check=True)
    output = ROOT/'dist'/'MotasDownloader-Portable'
    shutil.copytree(ROOT/'bin',output/'bin',dirs_exist_ok=True)
    for name in ('LICENSE.txt','README.md','THIRD-PARTY.md'):
        shutil.copy2(ROOT/name,output/name)
    if (ROOT/'Licencas').exists():
        shutil.copytree(ROOT/'Licencas',output/'Licencas',dirs_exist_ok=True)
    subprocess.run([str(output/'SpotDL-worker.exe'),'--self-test-tags'],cwd=ROOT,check=True)
    with zipfile.ZipFile(ROOT/'dist'/'MotasDownloader-Portable.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in output.rglob('*'):
            relative = path.relative_to(output)
            if path.is_file() and relative.parts[0] not in ('Dados', 'Downloads'):
                archive.write(path, Path(output.name)/relative)
    print('Ready: dist/MotasDownloader-Portable.zip')

if __name__ == '__main__':
    main()
