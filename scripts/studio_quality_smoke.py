"""Geometry truth, quota policy, and automatic narration budgeting regression checks."""
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from cube_geometry import EXAMPLE, TRANSFER, frames, vertices, edge, same_edge, classified_nets, cube_nets
from model_gateway import ModelGateway
from configuration import DEFAULTS, merge, resolve_config
from pipeline import VideoPipeline

def geometry():
    nets=cube_nets()
    assert len(nets)==11
    assert {k:len(v) for k,v in classified_nets().items()}=={'141':6,'132':3,'222':1,'33':1}
    for cells in nets:
        net={str(i):p for i,p in enumerate(cells)}
        folded=frames(net)
        all_vertices={tuple(np.round(v,8)) for f in folded.values() for v in vertices(f)}
        assert len(all_vertices)==8
        edges=Counter(tuple(sorted(tuple(np.round(v,8)) for v in edge(f,side))) for f in folded.values() for side in ('top','bottom','left','right'))
        assert len(edges)==12 and set(edges.values())=={2}
        by_pos={p:k for k,p in net.items()}
        for amount in np.linspace(0,1,11):
            partial=frames(net,amount)
            for name,(x,y) in net.items():
                for delta,a,b in [((1,0),'right','left'),((0,1),'top','bottom')]:
                    other=by_pos.get((x+delta[0],y+delta[1]))
                    if other is not None:assert same_edge(edge(partial[name],a),edge(partial[other],b))
    original=frames(EXAMPLE,root='B');transferred=frames(TRANSFER,root='B')
    assert same_edge(edge(original['E'],'top'),edge(original['D'],'top'))
    for side in ('bottom','left','right'):assert not same_edge(edge(original['E'],'top'),edge(original['D'],side))
    assert same_edge(edge(original['D'],'top'),edge(transferred['D'],'bottom'))
    for name in original:
        a,u,v=original[name];b,uu,vv=transferred[name]
        assert np.allclose(a,b)
        assert np.allclose(u,-uu if name=='D' else uu)
        assert np.allclose(v,-vv if name=='D' else vv)
    print('PASS: all 11 nets have 8 vertices/12 double-incidence edges; hinges stay attached throughout motion; E/D answer and 180 degree transfer verified.')

def quota():
    for role,error,should_switch in [('text','insufficient_quota',True),('text','429 rate limit',False),('text','401 invalid API key',False),('vision','insufficient_quota',False)]:
        gateway=ModelGateway.__new__(ModelGateway)
        gateway.role=role;gateway.settings={'model':'kimi-k3','quota_fallback_model':'deepseek-v4.1-flash','base_url':'https://original.example/v1','api_key':'test-secret'}
        before=gateway.settings.copy();calls=[]
        def request(*args):
            calls.append(gateway.settings['model'])
            if len(calls)==1:raise RuntimeError(error)
            return 'ok',{}
        gateway._request=request
        try:result=gateway.request('test')
        except RuntimeError:assert not should_switch
        else:assert should_switch and result==('ok',{})
        assert gateway.settings['base_url']==before['base_url'] and gateway.settings['api_key']==before['api_key']
        assert calls==(['kimi-k3','deepseek-v4.1-flash'] if should_switch else ['kimi-k3'])
    print('PASS: fallback only on text-model quota exhaustion; rate limit, auth failure and visual model never trigger a switch.')

class BudgetGateway:
    def __init__(self,settings,role='text',**kwargs):self.settings=settings;self.usage={};self.storyboards=0
    def json(self,prompt,validator,**kwargs):
        if '阶段: OUTLINE' in prompt:
            value={'topic':'测试','target_audience':'测试','warnings':[],'sections':[{'id':'section_1','title':'测试','goal':'测试','key_points':['测试'],'sources':[]}]}
        else:
            self.storyboards+=1
            narration='这段旁白需要自动缩短。'*8 if self.storyboards==1 else '精简旁白。'
            value={'sections':[{'id':'section_1','title':'测试','beats':[{'narration':narration,'caption':'字幕','visual':'图形','duration_seconds':1}]}]}
        validator(value);return value

def audio_budget():
    config=resolve_config(merge(DEFAULTS,{'text':{'model':'test','api_key':'test'},'tts':{'provider':'none'},'video':{'target_duration':3,'pause_seconds':.1}}))
    with tempfile.TemporaryDirectory() as tmp,patch('pipeline.ModelGateway',BudgetGateway):
        root=Path(tmp)
        pipe=VideoPipeline('时长预算测试',config,root/'output',project=root)
        pipe.run(stop_after='audio')
        timing=json.loads((root/'output/timing.json').read_text(encoding='utf8'))
        assert pipe.text.storyboards==2
        assert timing['sections'][0]['beats'][0]['narration']=='精简旁白。'
        assert abs(timing['sections'][0]['beats'][0]['duration']-3)<1e-6
    print('PASS: measured audio overrun automatically revises narration and reaches target without truncating speech.')

if __name__=='__main__':geometry();quota();audio_budget()
