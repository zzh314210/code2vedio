"""Verify real silent lead-ins, subtitle offsets, fixed timing, and cache stability."""
import json
import math
import sys
import tempfile
import wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from pipeline import VideoPipeline


class ToneNarrator:
    calls=0
    def synthesize(self,text,destination):
        self.calls+=1
        destination.parent.mkdir(parents=True,exist_ok=True)
        with wave.open(str(destination),'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(24000)
            stream.writeframes(b''.join(int(1000*math.sin(i*2*math.pi*220/24000)).to_bytes(2,'little',signed=True) for i in range(24000)))
        return {'duration':1,'subtitles':[{'start':0,'end':1,'text':text}]}


with tempfile.TemporaryDirectory() as temporary:
    pipe=VideoPipeline.__new__(VideoPipeline)
    pipe.output=Path(temporary)
    pipe.config={'video':{'fps':30,'pause_seconds':.1,'fixed_beat_durations':True},'tts':{'provider':'test'}}
    pipe.narrator=ToneNarrator()
    section={'id':'section_1','beats':[{'narration':'Read then explain','duration_seconds':6,'lead_in_seconds':2.5}]}
    pipe.prepare_audio(section)
    beat=section['beats'][0]
    assert beat['duration']==6
    assert beat['subtitles']==[{'start':2.5,'end':3.5,'text':'Read then explain'}]
    with wave.open(beat['audio'],'rb') as stream:
        rate=stream.getframerate();prefix=stream.readframes(round(rate*2.5));remainder=stream.readframes(rate)
        assert not any(prefix) and any(remainder)
        assert abs(stream.getnframes()/rate-3.5)<.001
    pipe.prepare_audio(section)
    assert pipe.narrator.calls==1 and beat['subtitles'][0]['start']==2.5
    beat['lead_in_seconds']=3
    pipe.prepare_audio(section)
    assert pipe.narrator.calls==2 and beat['subtitles'][0]['start']==3
    with wave.open(beat['audio'],'rb') as stream:assert abs(stream.getnframes()/stream.getframerate()-4)<.001
print('PASS: exactly 2.5s digital silence precedes speech, subtitle timestamps shift, beat remains 6s, cache does not add silence twice, changed lead-in invalidates audio.')
