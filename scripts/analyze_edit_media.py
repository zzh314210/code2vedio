"""Isolated CPU scene/transcript analysis. No cloud requests; models are preinstalled."""
import argparse,json,os
from pathlib import Path
from opencc import OpenCC
converter=OpenCC('t2s')
p=argparse.ArgumentParser();p.add_argument('video');p.add_argument('audio');p.add_argument('output');p.add_argument('--model',required=True);p.add_argument('--duration',type=float,required=True);p.add_argument('--context',default='');a=p.parse_args()
os.environ['OMP_NUM_THREADS']='2';os.environ['OPENBLAS_NUM_THREADS']='2'
from scenedetect import open_video,SceneManager,AdaptiveDetector
video=open_video(a.video);manager=SceneManager();manager.add_detector(AdaptiveDetector(min_scene_len=30));manager.detect_scenes(video,show_progress=False,frame_skip=2)
scenes=[{'start':s.get_seconds(),'end':e.get_seconds()} for s,e in manager.get_scene_list(start_in_scene=True)]
if not scenes:scenes=[{'start':0,'end':a.duration}]
transcript=[]
if a.audio!='-':
 from faster_whisper import WhisperModel
 model=WhisperModel(a.model,device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
 segments,info=model.transcribe(a.audio,beam_size=1,best_of=1,vad_filter=True,condition_on_previous_text=False,initial_prompt=a.context[:300] or None)
 for s in segments:
  if s.no_speech_prob<.8 and s.text.strip():transcript.append({'start':round(s.start,3),'end':round(s.end,3),'text':converter.convert(s.text.strip())})
Path(a.output).write_text(json.dumps({'scenes':scenes,'transcript':transcript},ensure_ascii=False))
