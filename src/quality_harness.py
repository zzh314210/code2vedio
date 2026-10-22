"""Frozen acceptance contracts, evidence-bound reviews and durable bounded repairs.

Model opinions are evidence, never the authority to bypass deterministic gates.
Only validated approved-plan coverage plus all host checks can release a film.
"""
import fcntl
from contextlib import contextmanager
import hashlib
import json
import math
import re
import subprocess
import time
from pathlib import Path

from media import ffmpeg_binary, probe, sample_frames, fit_audio, concat, write_subtitles, mux
from video_project import write_json

DEFAULT_POLICY = dict(max_cost_cents=1000, planning_revisions=2, code_revisions=2, render_revisions=2,
                      visual_revisions=1, final_revisions=1, max_model_calls=60, sample_seconds=2)


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


class QualityBudgetExceeded(RuntimeError):
    stop_retry = True


class QualityRejected(RuntimeError):
    stop_retry = True
    def __init__(self, report):
        self.report = report
        failures = [x.get('detail', x.get('requirement', x.get('id', '未通过'))) for x in report.get('checks', []) if x.get('status') != 'pass']
        super().__init__('质量验收未通过：' + '；'.join(failures)[:1400])


class QualityBudget:
    def __init__(self, directory, policy):
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'budget.json'
        self.policy = {**DEFAULT_POLICY, **policy}
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'calls': [], 'revisions': {}}

    def reload(self):
        if self.path.exists():self.state=json.loads(self.path.read_text())

    def save(self): write_json(self.path, self.state)

    @contextmanager
    def locked(self):
        # Shared by worker, planning edits and restarts; no lost concurrent updates.
        with (self.directory/'budget.lock').open('a') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(stream,fcntl.LOCK_UN)

    def take_call(self, role, stage, model):
        with self.locked():
            self.reload()
            if len(self.state['calls']) >= self.policy['max_model_calls']:
                raise QualityBudgetExceeded(f"已达到本任务最多 {self.policy['max_model_calls']} 次模型调用，已停止；重试不会重置用量，请创建新版本后继续。")
            self.state['calls'].append({'role': role, 'stage': stage, 'model': model, 'at': time.time()})
            self.save()

    def take_revision(self, stage, target='film'):
        with self.locked():
            self.reload()
            key = stage + ':' + target
            used = self.state['revisions'].get(key, 0)
            limit = self.policy[stage + '_revisions']
            if used >= limit:
                raise QualityBudgetExceeded(f'“{target}”已达到'+{'planning':'规划','code':'动画代码','render':'渲染修复','visual':'镜头验收','final':'完整成片'}.get(stage,stage)+f'环节最多 {limit} 次自动修改，未通过验收，已停止并保留报告。')
            self.state['revisions'][key] = used + 1
            self.save()
            return used + 1

def beat_map(storyboard):
    result = {}
    for section in storyboard['sections']:
        for i, beat in enumerate(section['beats'], 1):
            result[f"{section['id']}:{i}"] = {'section_id': section['id'], 'narration': beat['narration'], 'visual': beat.get('visual', ''), 'caption': beat.get('caption', '')}
    return result


class QualityHarness:
    def __init__(self, pipe):
        self.pipe = pipe; self.policy = {**DEFAULT_POLICY, **pipe.config.get('quality', {})}
        for key in ('planning_revisions','code_revisions','render_revisions','visual_revisions','final_revisions'):
            if type(self.policy[key]) is not int or not 0 <= self.policy[key] <= 5: raise ValueError('自动修改次数需为0至5的整数')
        if type(self.policy['max_model_calls']) is not int or not 1 <= self.policy['max_model_calls'] <= 120: raise ValueError('模型调用总上限需为1至120')
        if not .5 <= float(self.policy['sample_seconds']) <= 3: raise ValueError('验收采样间隔需为0.5至3秒')
        self.directory = pipe.output / 'quality'; self.directory.mkdir(exist_ok=True)
        self.budget = QualityBudget(self.directory, self.policy)
        self.contract = None

    def ensure_contract(self, outline, board):
        self.pipe.event('criteria', 'running', '根据已确认的大纲与分镜制定并冻结验收标准')
        approved = {'outline': outline, 'storyboard': board}
        plan_hash = digest(approved)
        path = self.directory / ('contract-' + plan_hash + '.json')
        mapping = beat_map(board)
        if path.exists():
            contract = json.loads(path.read_text())
            if contract.get('contract_hash') != digest({k:v for k,v in contract.items() if k!='contract_hash'}) or contract['plan_hash'] != plan_hash:
                raise ValueError('验收标准完整性校验失败，不允许改写标准绕过验收')
        else:
            def validate(value):
                checks = value.get('checks')
                if not isinstance(checks, list) or not len(mapping)*2 <= len(checks) <= len(mapping)*4+4: raise ValueError('每个镜头都需要内容与画面两类验收要求')
                ids = set(); coverage = {bid:set() for bid in mapping}
                for check in checks:
                    if not isinstance(check, dict): raise ValueError('验收条目需为对象')
                    cid = check.get('id'); bid = check.get('beat_id'); category = check.get('category')
                    if not isinstance(cid,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',cid) or cid in ids: raise ValueError('验收条目标识重复或无效')
                    if bid not in mapping or category not in ('content','visual','coherence'): raise ValueError('验收条目必须绑定已确认的镜头')
                    if not isinstance(check.get('requirement'),str) or not 5 <= len(check['requirement']) <= 800: raise ValueError('验收要求需具体、可观察，5至800字')
                    ids.add(cid); coverage[bid].add(category)
                if any(not {'content','visual'} <= groups for groups in coverage.values()): raise ValueError('不得遗漏任何镜头的内容或可视化验收')
            prompt = '''你是独立的教学视频验收规划师。只根据已经确认的大纲与分镜制定可观察、可证伪的验收要求；聚焦正确性、可读性、必要的可视化与逻辑衔接，不把装饰性滑入、淡入、轻抖、脉冲或无法通过截图序列证明的精确毫秒时长设为门禁；不修改题目、事实、结论、旁白或镜头。每个镜头至少一条content（原理/数字/角色/字幕与旁白一致）及一条visual（可视化清楚、无重叠裁切、图形真实表达原理），可加coherence（前后衔接）。不要用“美观即可”“整体通过”代替具体要求。不要要求画面包含分镜没有批准的信息，不把动画过渡状态当成事实错误。返回JSON且只含checks数组，每项{id:英文唯一标识,beat_id:原镜头ID,category:content或visual或coherence,requirement:中文具体验收要求}。不输出思考或markdown。全部镜头：'''
            value = self.pipe.acceptance.json(prompt + json.dumps({'approved_plan':approved,'beats':mapping},ensure_ascii=False), validate)
            validate(value)
            baseline=[]
            for n,(bid,beat) in enumerate(mapping.items()):
                for category,requirement in [('content','画面中的人物、数字、标签、条件、结论必须与该镜头已确认的旁白和分镜一致，不得凭空加入事实。'),('visual','必须用实际图形、关系或运动解释本镜头含义，关键文字清晰可读，不能用满屏旁白代替可视化，不得重叠、裁切。'),('coherence','本镜头的角色与符号保持一致，动画推进、前后衔接不能引入相互矛盾的信息；对当前证据无法证实的要求标记不确定。')]:
                    baseline.append({'id':f'host_{n}_{category}','beat_id':bid,'category':category,'requirement':requirement})
            if {c['id'] for c in baseline}&{c['id'] for c in value['checks']}:raise ValueError('模型标准不得占用宿主标准ID')
            contract = {'schema_version':2, 'plan_hash':plan_hash, 'beats':mapping, 'checks':baseline+value['checks'],
                'host_rules':{'max_unplanned_silence_seconds':3.5,'max_blank_seconds':1.0,'duration_tolerance_seconds':.25,'complete_decode':True,'all_subtitles':True,'minimum_visual_evidence_per_beat':8},
                'scope':'完整媒体程序检查＋逐镜头密集采样模型审核；不是逐帧语义理解，也不将已确认稿件视为外部事实来源。'}
            contract['contract_hash'] = digest(contract)
            write_json(path, contract)
        self.contract = contract
        write_json(self.directory/'contract.json', contract)
        self.pipe.event('criteria','complete','验收标准已冻结；修改成片不会降低标准')
        return contract

    def timeline_check(self, board):
        checks=[]; cursor=0; transcript=[]
        for section in board['sections']:
            for i, beat in enumerate(section['beats'],1):
                bid=f"{section['id']}:{i}"; duration=beat['duration']; cues=beat.get('subtitles') or []
                valid=bool(cues);last=0;joined=''
                for j,cue in enumerate(cues):
                    start,end=cue.get('start'),cue.get('end');text=cue.get('text')
                    if not isinstance(start,(int,float)) or not isinstance(end,(int,float)) or not math.isfinite(start+end) or not 0<=start<end<=duration+.02 or start<last-.02 or not isinstance(text,str) or not text.strip():valid=False;continue
                    last=end;joined+=text
                    transcript.append({'id':f'{bid}:{j+1}','beat_id':bid,'start':round(cursor+start,3),'end':round(cursor+end,3),'text':text})
                normalize=lambda text:re.sub(r'[\W_]+','',text).casefold()
                valid=valid and normalize(joined)==normalize(beat['narration'])
                checks.append({'id':bid+'_subtitles','status':'pass' if valid else 'fail','detail':'完整逐句字幕与旁白一致，时间不越界' if valid else f'{bid}字幕缺失、时序错误或未覆盖完整旁白','section_id':section['id']})
                cursor+=duration
        report={'passed':all(c['status']=='pass' for c in checks),'checks':checks,'transcript':transcript,'duration':cursor,'contract_hash':self.contract['contract_hash']}
        write_json(self.directory/'timeline.json',report)
        if not report['passed']:raise QualityRejected(report)
        return report

    def positions(self, board, duration):
        positions=set(); cursor=0
        for section in board['sections']:
            for beat in section['beats']:
                length=float(beat['duration'])
                positions.update(round(min(duration-.02,cursor+length*f),3) for f in (.05,.15,.30,.45,.60,.75,.85,.95))
                t=cursor+.1
                while t<cursor+length-.02:
                    positions.add(round(t,3));t+=self.policy['sample_seconds']
                cursor+=length
        if cursor>duration+.25:raise ValueError('视频长度短于已批准的完整镜头时间线')
        positions=sorted(t for t in positions if 0<=t<duration)
        if len(positions)>960:raise ValueError('验收帧超过资源上限，请增大采样间隔')
        return positions

    def section_media(self, video, board):
        beats=[b for section in board['sections'] for b in section['beats']]
        if not all(b.get('audio') and Path(b['audio']).is_file() for b in beats):return video
        mode=self.pipe.config['video'].get('subtitle_mode','soft')
        fingerprint=digest({'video':file_hash(video),'audio':[file_hash(b['audio']) for b in beats],'beats':beats,'subtitle_mode':mode})
        directory=self.directory/'section-media'/fingerprint;directory.mkdir(parents=True,exist_ok=True)
        destination=directory/'review.mp4';receipt=directory/'receipt.json'
        if destination.exists() and receipt.exists() and json.loads(receipt.read_text()).get('media_sha256')==file_hash(destination):return destination
        audio=[]
        for n,beat in enumerate(beats):
            padded=directory/f'audio-{n}.wav';fit_audio(Path(beat['audio']),padded,beat['duration']);audio.append(padded)
        concat(audio,directory/'narration.wav',audio=True)
        duration=write_subtitles(beats,directory/'subtitles.srt')
        mux(video,directory/'narration.wav',directory/'subtitles.srt',destination,duration,subtitle_mode=mode)
        write_json(receipt,{'fingerprint':fingerprint,'media_sha256':file_hash(destination)})
        for padded in audio:padded.unlink(missing_ok=True)
        return destination

    def review_video(self, video, board, scope):
        if not self.pipe.vision:raise ValueError('质量验收需要支持图片的视觉审核模型')
        if scope!='final':video=self.section_media(video,board)
        review_policy_hash=digest({'sample_seconds':self.policy['sample_seconds'],'subtitle_mode':self.pipe.config['video'].get('subtitle_mode','soft'),'review_schema':4})
        media_hash=file_hash(video); path=self.directory/(scope+'-'+media_hash+'.json')
        if path.exists():
            saved=json.loads(path.read_text())
            if saved.get('review_policy_hash')==review_policy_hash and saved.get('contract_hash')==self.contract['contract_hash'] and saved.get('media_sha256')==media_hash and saved.get('report_hash')==digest({k:v for k,v in saved.items() if k!='report_hash'}):return saved
        duration=probe(video)['duration']; positions=self.positions(board,duration)
        frame_dir=self.directory/(scope+'-'+media_hash[:16]);frames=sample_frames(video,frame_dir,count=len(positions),positions=positions)
        timeline=[];cursor=0
        for section in board['sections']:
            for i,beat in enumerate(section['beats'],1):
                timeline.append({'id':f"{section['id']}:{i}",'section_id':section['id'],'start':cursor,'end':cursor+beat['duration'],'narration':beat['narration'],'subtitles':beat.get('subtitles',[])})
                cursor+=beat['duration']
        evidence=[{'id':f'f{i:04}','seconds':t,'beat_id':next(b['id'] for b in timeline if b['start']<=t<b['end'])} for i,t in enumerate(positions)]
        checks=[];batches=[]
        # Every batch carries the current beat's beginning, middle and end.
        # Adjacent beats supply transition context, never incomplete extra criteria.
        for n,beat in enumerate(timeline):
            own=[i for i,e in enumerate(evidence) if e['beat_id']==beat['id']]
            anchors=list(dict.fromkeys(min(own,key=lambda i:abs(evidence[i]['seconds']-(beat['start']+(beat['end']-beat['start'])*f))) for f in (.15,.5,.85)))
            adjacent=([own[0]-1] if own[0]>0 else [])+([own[-1]+1] if own[-1]+1<len(evidence) else [])
            rest=[i for i in own if i not in anchors]
            room=12-len(anchors)-len(adjacent)
            for k in range(0,max(1,len(rest)),room):
                batches.append((beat['id'],sorted(set(anchors+adjacent+rest[k:k+room]))))
        for number,(bid,indices) in enumerate(batches):
            batch=[evidence[i] for i in indices]
            expected=[x for x in self.contract['checks'] if x['beat_id']==bid]
            expected_ids={x['id'] for x in expected};frame_ids={x['id'] for x in batch}
            prompt='''你是严格的视频验收员。按冻结标准逐项核对附图、完整旁白与全部字幕。附图按时间排列，应核对镜头内动画推进及跨镜头衔接。检查角色/数值/因果、表达清晰、无遮挡裁切、字幕可读、图形是否真正解释内容。不是只读字幕判通过；必须观察画面。字幕只在配音时出现，合法转场不算错误。评价本镜头完整推进，结论在镜头末尾揭示是正常讲解，不要求开头就显示答案。相邻镜头截图仅用于衔接判断。不要擅自扩充验收要求；仅标准明确要求且影响讲解的动态过程才作为门禁，普通淡入、滑入、轻抖、脉冲等装饰不属于角色或逻辑一致性标准。截图不能证实的必要教学动态效果标uncertain，不能猜测通过。不允许改变、遗漏、降低验收标准。只返回JSON：{"checks":[{"id":"原标准ID","status":"pass或fail或uncertain","frame_ids":["本批证据ID"],"detail":"具体看到什么、与要求是否一致；失败给出可执行修改"}]}。不得用自报总分或passed代替逐项证据。必须包含本批每条标准且恰好一次。'''
            context={'frozen_checks':expected,'complete_narration_and_subtitles':timeline,'frames':batch,'subtitle_mode':self.pipe.config['video'].get('subtitle_mode','soft'),'scope':scope,'approved_plan':self.contract['beats'],'media_note':'章节审核与最终成片均已按所选字幕模式合成。字幕关闭时不要求出现字幕，字幕中的原话与画面标签允许同义表达。每批只评价提供证据覆盖的镜头，不假设没有给出的画面。'}
            def validate(value):
                rows=value.get('checks')
                if not isinstance(rows,list) or len(rows)!=len(expected):raise ValueError('必须完整评价本批全部验收标准')
                ids=set()
                for row in rows:
                    cid=row.get('id'); refs=row.get('frame_ids')
                    if cid not in expected_ids or cid in ids or row.get('status') not in ('pass','fail','uncertain'):raise ValueError('验收条目缺失、重复或状态无效')
                    if not isinstance(refs,list) or not refs or any(f not in frame_ids for f in refs):raise ValueError('每项结论必须引用本批实际帧证据')
                    criterion=next(x for x in expected if x['id']==cid)
                    if not any(x['id'] in refs and x['beat_id']==criterion['beat_id'] for x in batch):raise ValueError('证据帧必须属于该验收镜头')
                    if not isinstance(row.get('detail'),str) or not 5<=len(row['detail'])<=1400:raise ValueError('必须说明具体验收依据')
                    ids.add(cid)
            batch_path=frame_dir/f'batch-{number:04}.json'
            batch_fingerprint=digest({'contract':self.contract['contract_hash'],'frames':batch,'media':media_hash,'expected':expected,'review_policy_hash':review_policy_hash})
            cached=json.loads(batch_path.read_text()) if batch_path.exists() else {}
            if cached.get('fingerprint')==batch_fingerprint:
                value=cached['result'];validate(value)
            else:
                value=self.pipe.vision.json(prompt+json.dumps(context,ensure_ascii=False),validate,images=[frames[i] for i in indices]);validate(value)
                write_json(batch_path,{'fingerprint':batch_fingerprint,'result':value})
            for row in value['checks']:
                criterion=next(x for x in expected if x['id']==row['id'])
                checks.append({**row,'beat_id':criterion['beat_id'],'section_id':self.contract['beats'][criterion['beat_id']]['section_id'],'requirement':criterion['requirement'],'evidence_seconds':[e['seconds'] for e in batch if e['id'] in row['frame_ids']]})
        expected_all={c['id'] for c in self.contract['checks'] if c['beat_id'] in {x['id'] for x in timeline}}
        passed=bool(checks) and {c['id'] for c in checks}==expected_all and all(c['status']=='pass' for c in checks)
        report={'passed':passed,'checks':checks,'contract_hash':self.contract['contract_hash'],'media_sha256':media_hash,'frame_count':len(frames),'sample_seconds':self.policy['sample_seconds'],'scope':scope,'full_transcript':timeline,'review_policy_hash':review_policy_hash}
        report['report_hash']=digest(report)
        write_json(path,report)
        return report

    def final_checks(self, video, board, narration):
        checks=[];expected=sum(b['duration'] for s in board['sections'] for b in s['beats']);details=probe(video)
        required={'video','audio'}|({'subtitle'} if self.pipe.config['video'].get('subtitle_mode')!='off' else set())
        checks.append({'id':'streams','status':'pass' if required<={s['type'] for s in details['streams']} else 'fail','detail':'成片需要完整视频、声音及所选字幕轨'})
        checks.append({'id':'duration','status':'pass' if abs(details['duration']-expected)<=.25 else 'fail','detail':'成片时长必须覆盖完整镜头，不得截断旁白'})
        result=subprocess.run([ffmpeg_binary(),'-hide_banner','-xerror','-err_detect','explode','-threads','2','-i',str(video),'-vf','blackdetect@dark=d=1:pix_th=0.02:pic_th=0.995,negate,blackdetect@white=d=1:pix_th=0.02:pic_th=0.995','-f','null','-'],capture_output=True,text=True,timeout=600)
        (self.directory/'decode.log').write_text(result.stderr[-200000:])
        checks.append({'id':'decode','status':'pass' if result.returncode==0 else 'fail','detail':'逐帧完整解码检查，不能存在损坏帧或轨道'})
        blacks=[tuple(map(float,m)) for m in re.findall(r'black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)',result.stderr)]
        blank_sections=[];cursor=0
        for section in board['sections']:
            end=cursor+sum(b['duration'] for b in section['beats'])
            if any(a<end and b>cursor for a,b,_ in blacks):blank_sections.append(section['id'])
            cursor=end
        checks.append({'id':'blank','status':'pass' if not blacks else 'fail','detail':'画面不能出现超过1秒的全黑或全白空白','intervals':blacks,'section_ids':blank_sections})
        sound=subprocess.run([ffmpeg_binary(),'-hide_banner','-threads','2','-i',str(narration),'-af','silencedetect=noise=-42dB:d=3.5','-f','null','-'],capture_output=True,text=True,timeout=300)
        (self.directory/'silence.log').write_text(sound.stderr[-100000:])
        starts=[float(x) for x in re.findall(r'silence_start: ([\d.]+)',sound.stderr)];ends=[float(x) for x in re.findall(r'silence_end: ([\d.]+)',sound.stderr)]
        intervals=[(start,ends[i] if i<len(ends) else expected) for i,start in enumerate(starts)]
        allowed=[];cursor=0
        for section in board['sections']:
            for beat in section['beats']:
                hold=float(beat.get('hold_after_seconds',0));allowed.append((cursor+beat['duration']-hold-.25,cursor+beat['duration']+.05)) if hold>0 else None;cursor+=beat['duration']
        bad=[(a,b) for a,b in intervals if b-a>3.5 and not any(a>=x and b<=y for x,y in allowed)]
        checks.append({'id':'silence','status':'pass' if sound.returncode==0 and not bad else 'fail','detail':'旁白不能存在超过3.5秒的非规划静音；已批准的回忆停顿除外','intervals':bad})
        # Verify actual muxed captions, not only the intended subtitle cues.
        self.timeline_check(board)
        subtitle_ok=True
        if self.pipe.config['video'].get('subtitle_mode','soft')!='off':
            extracted=subprocess.run([ffmpeg_binary(),'-hide_banner','-loglevel','error','-i',str(video),'-map','0:s:0','-f','srt','-'],capture_output=True,text=True,timeout=120)
            blocks=re.split(r'\n\s*\n',extracted.stdout.strip())
            actual=''.join(''.join(block.splitlines()[2:]) for block in blocks)
            expected_text=''.join(b['narration'] for section in board['sections'] for b in section['beats'])
            normalize=lambda text:re.sub(r'[\W_]+','',text).casefold()
            subtitle_ok=extracted.returncode==0 and normalize(actual)==normalize(expected_text)
        checks.append({'id':'subtitles','status':'pass' if subtitle_ok else 'fail','detail':'实际成片字幕必须覆盖完整旁白；关闭可见字幕时仍保留完整内部时序核对'})
        report={'passed':all(c['status']=='pass' for c in checks),'checks':checks,'contract_hash':self.contract['contract_hash'],'media_sha256':file_hash(video)}
        write_json(self.directory/'technical.json',report)
        return report

    def report(self, host, visual, parts=None):
        parts=parts or []
        report={'schema_version':1,'passed':host['passed'] and visual['passed'] and bool(parts) and all(p['passed'] for p in parts),'checks':host['checks']+visual['checks'],'contract_hash':self.contract['contract_hash'],'media_sha256':host['media_sha256'],'frames':visual['frame_count'],'model_calls':len(self.budget.state['calls']),'revisions':self.budget.state['revisions'],'policy':self.policy,'parts':parts}
        report['report_hash']=digest(report)
        write_json(self.directory/'acceptance.json',report)
        return report


def verify_release(output, video):
    """Fail closed for harness jobs, bind delivery to the approved media and plan."""
    output=Path(output)
    manifest=json.loads((output/'manifest.json').read_text())
    if not manifest.get('config',{}).get('quality',{}).get('enabled'):return
    contract=json.loads((output/'quality/contract.json').read_text())
    report=json.loads((output/'quality/acceptance.json').read_text())
    if contract.get('contract_hash')!=digest({k:v for k,v in contract.items() if k!='contract_hash'}):raise ValueError('验收标准已改变')
    if report.get('report_hash')!=digest({k:v for k,v in report.items() if k!='report_hash'}):raise ValueError('验收报告完整性校验失败')
    approved={name:json.loads((output/(name+'.json')).read_text()) for name in ('outline','storyboard')}
    if digest(approved)!=contract['plan_hash']:raise ValueError('验收报告与已确认的规划不一致')
    if not report.get('passed') or report.get('contract_hash')!=contract['contract_hash'] or report.get('media_sha256')!=file_hash(video):raise ValueError('成片未通过当前版本验收')
    ids={c['id'] for c in report.get('checks',[]) if c.get('status')=='pass'}
    if not ({c['id'] for c in contract['checks']}|{'streams','duration','decode','blank','silence','subtitles'})<=ids or any(c.get('status')!='pass' for c in report.get('checks',[])):raise ValueError('存在未通过或遗漏的成片检查')
    required={s['id'] for s in approved['storyboard']['sections']}
    parts=report.get('parts',[])
    if {p['section_id'] for p in parts}!=required or any(not p['passed'] for p in parts):raise ValueError('章节验收未全部通过')
    return report
