"""Final media and proof handoff checks; sampled vision remains a separate check."""
import hashlib
from pathlib import Path


def final_receipt(proof,storyboard,final,details,contract,render_receipts):
    contract.validate_plan_handoff(storyboard,proof,'storyboard')
    beats=[b for s in storyboard['sections'] for b in s['beats']]
    scenes=[s for r in render_receipts for s in r['scenes']]
    if len(beats)!=6 or len(scenes)!=len(beats):raise ValueError('最终媒体缺少必要的推理场景')
    for b,s in zip(beats,scenes):
        if s['proof_hash']!=proof['proof_hash'] or s['scene_id']!=b['scene_id'] or s['narration_sha256']!=contract.digest(b['narration']):raise ValueError('最终图解与已验证推理、旁白不一致')
        if abs(s['duration']-b['duration'])>.04:raise ValueError('画面时长与真实配音时间线不一致')
        if not b.get('subtitles'):raise ValueError('此图解需要逐句字幕时序，配音未提供可用字幕')
    duration=sum(b['duration'] for b in beats)
    if abs(details['duration']-duration)>.2:raise ValueError('成片时长与证明场景不一致')
    if not {'video','audio'}<={s['type'] for s in details['streams']}:raise ValueError('成片音视频或字幕轨缺失')
    h=hashlib.sha256()
    with Path(final).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return {'schema_version':1,'proof_hash':proof['proof_hash'],'final_sha256':h.hexdigest(),'duration':duration,'scenes':len(scenes),
            'engines':sorted({r['engine'] for r in render_receipts}),'checks':['compiled narration preserved','render scene proof hashes','measured audio timing','timed subtitles present','final media streams and duration'],
            'scope':'Stage/media integrity. Natural-language translation uses separate semantic audit; sampled visual review is not exhaustive frame verification.'}
