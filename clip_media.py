"""Validated, frame-accurate local trimming using the bundled FFmpeg."""
import json
import tempfile
from subtitles import read_cues, write_ass
import math
import os
from pathlib import Path
import re
import subprocess
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import PostProcessingError

def clock(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}'

def parse_clock(value):
    if not re.fullmatch(r'\d{2,}:\d{2}:\d{2}', value.strip()):
        raise ValueError('Use o formato 00:00:00 para início e fim.')
    h,m,s = map(int,value.strip().split(':'))
    if m > 59 or s > 59:
        raise ValueError('Minutos e segundos devem estar entre 00 e 59.')
    return h*3600+m*60+s

def validate_range(start, end, duration):
    a,b = parse_clock(start),parse_clock(end)
    if not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Analise um vídeo com duração definida para recortar.')
    if a >= b:
        raise ValueError('O fim precisa ser maior que o início.')
    if b > duration:
        raise ValueError(f'O fim não pode ultrapassar {clock(duration)}.')
    return a,b

class ClipMediaPP(PostProcessor):
    def __init__(self, downloader, start, end, ffmpeg, audio_only=False, log=None, subtitles=None):
        super().__init__(downloader)
        self.subtitles = subtitles
        self.start,self.end,self.ffmpeg,self.audio_only,self.log=start,end,ffmpeg,audio_only,log

    def run(self, info):
        source=Path(info['filepath'])
        dest=source.with_suffix('.wav' if self.audio_only else '.mp4')
        temp=dest.with_name(dest.stem+'.cutting'+dest.suffix)
        scratch=tempfile.TemporaryDirectory(prefix='motas-subs-')
        filters=['pad=ceil(iw/2)*2:ceil(ih/2)*2']
        if self.subtitles:
            track=(info.get('requested_subtitles') or {}).get(self.subtitles['code']) or {}
            subpath=track.get('filepath')
            if not subpath or not Path(subpath).is_file():
                scratch.cleanup()
                raise PostProcessingError('A legenda selecionada não foi baixada. Analise o link novamente.')
            cues=read_cues(subpath)
            if not cues:
                scratch.cleanup()
                raise PostProcessingError('A legenda está vazia ou em formato inválido.')
            probe=subprocess.check_output([str(Path(self.ffmpeg).with_name('ffprobe.exe')),'-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(source.resolve())],creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            stream=json.loads(probe)['streams'][0]
            write_ass(Path(scratch.name)/'subtitles.ass',cues,stream['width'],stream['height'],self.subtitles['size'],self.subtitles['color'])
            filters.append('ass=subtitles.ass')
        args=[self.ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-y',
              '-i',str(source.resolve()),'-map_metadata','-1','-map_chapters','-1']
        if self.end is not None:
            args += ['-ss',str(self.start),'-t',str(self.end-self.start)]
        if self.audio_only:
            args += ['-map','0:a:0','-vn','-c:a','pcm_s16le']
        else:
            # Software encoder already present in the LGPL portable build.
            args += ['-map','0:v:0','-map','0:a:0?','-c:v','libopenh264','-b:v','8M',
                     '-pix_fmt','yuv420p','-vf',','.join(filters),
                     '-c:a','aac','-b:a','192k','-movflags','+faststart']
        args += [str(temp.resolve())]
        if self.log:
            self.log('Gravando legendas no vídeo…' if self.subtitles else f'Recortando {clock(self.start)} a {clock(self.end)}…')
        try:
            result=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                cwd=scratch.name,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if result.returncode:
                raise PostProcessingError('Não foi possível recortar: '+result.stderr[-1200:])
            os.replace(temp,dest)
        finally:
            scratch.cleanup()
            if temp.exists():
                temp.unlink()
        info['filepath'],info['ext']=str(dest),dest.suffix[1:]
        if self.end is not None:
            info['duration']=self.end-self.start
        return ([str(source)] if source!=dest else []),info
