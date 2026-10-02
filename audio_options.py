"""Audio options derived from extractor metadata, preserving language and format ID."""
import re

LANGUAGES = {'pt':'Português','pt-BR':'Português (Brasil)','pt-PT':'Português (Portugal)',
    'en':'Inglês','en-US':'Inglês (EUA)','en-GB':'Inglês (Reino Unido)',
    'es':'Espanhol','fr':'Francês','de':'Alemão','it':'Italiano','ja':'Japonês',
    'ko':'Coreano','ru':'Russo','zh':'Chinês','hi':'Hindi','ar':'Árabe'}

def audio_options(formats):
    candidates=[f for f in formats if f.get('vcodec')=='none' and f.get('acodec') not in (None,'none') and f.get('format_id') and not f.get('has_drm')]
    original_languages={f.get('language') for f in candidates if is_original(f)} - {None}
    def number(f,key,default=-1):
        value=f.get(key)
        return value if isinstance(value,(int,float)) else default
    def rank(f):
        original=is_original(f) or f.get('language') in original_languages
        return (original,number(f,'language_preference'),number(f,'quality'),
            number(f,'abr',number(f,'tbr')),number(f,'asr'),number(f,'audio_channels'))
    result={}
    for f in sorted(candidates,key=rank,reverse=True):
        language=f.get('language')
        name=LANGUAGES.get(language,language or 'Idioma não informado')
        original=is_original(f) or language in original_languages
        rate=f.get('abr') or f.get('tbr')
        quality=f'{round(rate)} kbps' if rate else 'taxa não informada'
        codec=f.get('acodec','').split('.')[0]
        codec='AAC' if codec=='mp4a' else codec.upper()
        label=f'{name}' + (' · original' if original else '') + f" · {quality} {f.get('ext','')} ({codec})"
        if label in result:
            label+=f" [{f['format_id']}]"
        result[label]=f['format_id']
    return result

def is_original(f):
    return f.get('language_preference') == 10 or bool(re.search(r'\boriginal\b',f.get('format_note',''),re.I))

def audio_selector(format_id=None):
    return format_id or 'bestaudio/best'

def combined_selector(video_id=None,audio_id=None):
    if audio_id:
        return f'{video_id or "bestvideo"}+{audio_id}'
    return f'{video_id}+bestaudio' if video_id else 'bestvideo+bestaudio/best'

def audio_suffix(formats,format_id):
    audio=[f for f in formats if f.get('vcodec')=='none' and f.get('acodec') not in (None,'none')]
    if len({f.get('language') for f in audio if f.get('language')}) < 2:
        return ''
    selected=next((f for f in audio if f.get('format_id')==format_id),{})
    tag=re.sub(r'[^a-zA-Z0-9_.-]','_',str(selected.get('language') or 'und')+' '+str(format_id))
    return f' [audio {tag}]'
