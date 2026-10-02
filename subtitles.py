import html
import json
import re
from pathlib import Path

SIZES = {'Automático': 48, 'Pequena': 38, 'Média': 48, 'Grande': 60}

def subtitle_choices(info):
    choices = []
    for field, automatic in [('subtitles', False), ('automatic_captions', True)]:
        for code, formats in (info.get(field) or {}).items():
            if code == 'live_chat' or not any(f.get('ext') in ('json3','vtt','srt') for f in formats):
                continue
            name = next((f.get('name') for f in formats if f.get('name')), code)
            pt = code.lower().split('-')[0] == 'pt'
            label = f'{name} [{code}] — ' + ('automática' if automatic else 'do autor')
            choices.append(dict(code=code, automatic=automatic, label=label,
                rank=(0 if pt and not automatic else 1 if pt else 2,
                      automatic, 0 if code.lower() == 'pt-br' else 1, code)))
    return sorted(choices, key=lambda c:c['rank'])

def read_cues(path):
    raw = Path(path).read_text(encoding='utf-8-sig')
    cues=[]
    if Path(path).suffix == '.json3':
        for e in json.loads(raw).get('events', []):
            text=''.join(s.get('utf8','') for s in e.get('segs',[])).strip()
            if text and e.get('dDurationMs',0)>0:
                start=e.get('tStartMs',0)/1000
                cues.append([start,start+e['dDurationMs']/1000,text])
    else:
        def seconds(value):
            parts=value.replace(',','.').split(':')
            return sum(float(p)*60**i for i,p in enumerate(reversed(parts)))
        for block in re.split(r'\n\s*\n',raw.replace('\r','')):
            lines=block.splitlines()
            for i,line in enumerate(lines):
                m=re.match(r'([\d:.,]+)\s+-->\s+([\d:.,]+)',line)
                if m:
                    text=html.unescape(re.sub(r'<[^>]*>','','\n'.join(lines[i+1:])))
                    if text.strip(): cues.append([seconds(m[1]),seconds(m[2]),text.strip()])
                    break
    normalized=[]
    for a,b,text in sorted(cues,key=lambda c:c[0]):
        text=html.unescape(text)
        if normalized and a < normalized[-1][1]:
            if text == normalized[-1][2]:
                normalized[-1][1]=max(b,normalized[-1][1]);continue
            normalized[-1][1]=a
        if b>a: normalized.append([a,b,text])
    return [c for c in normalized if c[1]>c[0]]

def write_ass(path, cues, width, height, size='Automático', color='Branca'):
    # Virtual canvas preserves proportional sizing at all source resolutions.
    canvas_h=1080
    canvas_w=round(canvas_h*width/height)
    font= SIZES[size] * min(1,canvas_w/1080)
    primary='&H0000FFFF' if color=='Amarela' else '&H00FFFFFF'
    margin=max(24,round(canvas_w*.04))
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {canvas_w}
PlayResY: {canvas_h}
WrapStyle: 0
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font},{primary},&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.4,0,2,{margin},{margin},54,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    def timestamp(value):
        cs=round(value*100)
        return f'{cs//360000}:{cs//6000%60:02d}:{cs//100%60:02d}.{cs%100:02d}'
    for a,b,text in cues:
        text=text.replace('\\','／').replace('{','(').replace('}',')').replace('\n',r'\N')
        header+=f'Dialogue: 0,{timestamp(a)},{timestamp(b)},Default,,0,0,0,,{text}\n'
    Path(path).write_text(header,encoding='utf-8')
