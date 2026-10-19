"""Discoverable Edge voices and short, cached public demonstrations (no user keys)."""
import asyncio
import json
import threading
from pathlib import Path

import edge_tts
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from media import ffmpeg_binary, run_command

ROOT=Path(__file__).resolve().parents[1]
CATALOG=Path(__file__).with_name('voice-catalog.json')
RECOMMENDED={
 'zh-CN-XiaoxiaoNeural':('晓晓','自然亲切 · 适合通用讲解'),
 'zh-CN-YunxiNeural':('云希','清晰明快 · 适合知识科普'),
 'zh-CN-YunjianNeural':('云健','沉稳有力 · 适合叙事解说'),
 'zh-CN-XiaoyiNeural':('晓伊','轻快柔和 · 适合故事表达'),
 'zh-CN-YunyangNeural':('云扬','正式清楚 · 适合新闻与课堂'),
 'zh-CN-YunxiaNeural':('云夏','年轻活泼 · 适合轻松内容'),
 'zh-TW-HsiaoChenNeural':('晓臻','自然柔和 · 台湾普通话'),
 'zh-TW-YunJheNeural':('云哲','温和清晰 · 台湾普通话'),
 'zh-HK-HiuMaanNeural':('晓曼','自然粤语 · 适合日常讲解'),
 'en-US-AriaNeural':('Aria','自然英语 · 适合演示与故事'),
 'en-US-GuyNeural':('Guy','沉稳英语 · 适合解说'),
 'en-US-JennyNeural':('Jenny','友好英语 · 适合教程'),
 'en-GB-SoniaNeural':('Sonia','英式英语 · 清晰温和'),
}
SAMPLE_LOCK=threading.Lock()


def catalog():
    if not CATALOG.is_file():raise HTTPException(503,'音色目录正在准备，请稍后重试。')
    voices=json.loads(CATALOG.read_text())
    result=[]
    for v in voices:
        name=v['ShortName']
        title,description=RECOMMENDED.get(name,(v.get('FriendlyName',name).split(' - ')[-1], ''))
        result.append({'id':name,'name':title,'description':description,'locale':v['Locale'],'gender':v['Gender'],
                       'recommended':name in RECOMMENDED,'sample_url':f'/api/voices/{name}/sample','sample_seconds':2})
    return sorted(result,key=lambda v:(not v['recommended'],not v['locale'].startswith('zh'),v['locale'],v['name']))


def sample(identity):
    voice=next((v for v in catalog() if v['id']==identity),None)
    if not voice:raise HTTPException(404,'音色不存在。')
    directory=ROOT/'private/voice-samples';directory.mkdir(parents=True,exist_ok=True)
    target=directory/(identity+'.mp3')
    if target.is_file():return target
    # Serialize cache misses so public previews cannot start unbounded synthesizers.
    if not SAMPLE_LOCK.acquire(blocking=False):raise HTTPException(429,'另一段试听正在生成，请稍后重试。')
    raw=directory/(identity+'.raw.mp3')
    temporary=directory/(identity+'.part.mp3')
    try:
        if target.is_file():return target
        text='你好，一起来听听我的声音。' if voice['locale'].startswith('zh') else 'Hello, let us bring your ideas to life.'
        async def generate():
            await asyncio.wait_for(edge_tts.Communicate(text,identity).save(str(raw)),40)
        asyncio.run(generate())
        run_command([ffmpeg_binary(),'-y','-i',str(raw),'-af','apad','-t','2','-ar','24000','-ac','1','-codec:a','libmp3lame','-b:a','96k',str(temporary)],timeout=30)
        temporary.replace(target)
        return target
    except HTTPException:raise
    except Exception as error:
        raise HTTPException(502,'此音色暂时无法试听，请换一个或稍后重试。') from error
    finally:
        raw.unlink(missing_ok=True);temporary.unlink(missing_ok=True);SAMPLE_LOCK.release()


def voice_router():
    router=APIRouter()
    @router.get('/api/voices')
    def voices():return {'voices':catalog(),'provider':'edge'}
    @router.get('/api/voices/{identity}/sample')
    def preview(identity:str):return FileResponse(sample(identity),media_type='audio/mpeg')
    return router
