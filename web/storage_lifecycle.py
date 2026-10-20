"""24-hour user artifacts; reviewed public examples live outside this lifecycle."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

from video_project import write_json

TTL = 24*60*60
ACTIVE = {'queued','running','revising','uploading','analyzing','rendering'}


def user_directory(root, kind, identity, owner):
    now=datetime.now(timezone.utc)
    return Path(root)/'users'/now.strftime('%Y-%m-%d')/(now.strftime('%H%M%S')+'-'+owner[:8]+'-'+kind+'-'+identity)


def records(root, filename):
    root=Path(root)
    return list(root.glob('*/'+filename))+list(root.glob('users/*/*/'+filename))


class UserStorage:
    def __init__(self, root, projects, private):
        self.root, self.projects, self.private=Path(root),Path(projects),Path(private)
        self.pinned=set()
        manifest=self.root/'deliverables/manifest.json'
        if manifest.is_file():
            for video in json.loads(manifest.read_text()).get('videos',[]):
                if video.get('project'):self.pinned.add((self.root/video['project']).resolve())
        for metadata in (self.root/'web/public/showcase').glob('*.json'):
            try:
                name=json.loads(metadata.read_text()).get('project')
                if name and Path(name).name==name:self.pinned.add((self.projects/name).resolve())
            except (OSError,ValueError):continue

    def permanent(self, project, record):
        return bool(record.get('permanent') or Path(project).resolve() in self.pinned or (Path(project)/'.permanent').is_file())

    def migrate(self):
        # Existing user work gets a visible 24-hour grace window on rollout.
        for name in ('studio_job.json','editing_job.json'):
            for path in records(self.projects,name):
                try:
                    record=json.loads(path.read_text())
                    if self.permanent(path.parent,record):
                        record['permanent']=True;record.pop('expires_at',None)
                    elif 'expires_at' not in record:
                        record['expires_at']=time.time()+TTL
                    else:continue
                    write_json(path,record)
                except (OSError,ValueError):continue

    def stamp(self, record, previous=None):
        project=record.get('project')
        if record.get('permanent') or (project and self.permanent(project,record)):
            record['permanent']=True;record.pop('expires_at',None);return
        record.setdefault('expires_at',time.time()+TTL)
        if record.get('status') in ('complete','awaiting_review','failed','cancelled') and previous!=record.get('status'):
            record['expires_at']=time.time()+TTL

    def expired_records(self, kind):
        result=[]
        for path in (self.private/'expired'/kind).glob('*.json'):
            try:result.append(json.loads(path.read_text()))
            except (OSError,ValueError):continue
        return result

    def collect(self, jobs, edits, queue=None, now=None):
        now=now or time.time();removed=[]
        # A queued revision still needs its original film and frozen inputs.
        protected={record.get('revision_parent') for record in jobs.values() if record.get('status') in ACTIVE}
        for kind,items in (('video',jobs),('edit',edits)):
            for identity,record in list(items.items()):
                if record.get('status')=='expired':
                    if now-record.get('expired_at',now)>7*TTL:
                        items.pop(identity,None);(self.private/'expired'/kind/(identity+'.json')).unlink(missing_ok=True)
                    continue
                if identity in protected or record.get('status') in ACTIVE or not record.get('expires_at') or record['expires_at']>now:continue
                if queue and (queue.has_pending(identity) or queue.has_pending(identity+':advice')):continue
                project=Path(record.get('project') or (self.projects/('edit-'+identity)))
                if project.is_symlink() or not project.resolve().is_relative_to(self.projects.resolve()) or project.resolve()==self.projects.resolve():continue
                if self.permanent(project,record):continue
                marker=project/('studio_job.json' if kind=='video' else 'editing_job.json')
                if not marker.is_file():continue
                # Persist a tiny tombstone first so links fail clearly after cleanup.
                expired={k:v for k,v in record.items() if k in ('id','owner_id','prompt','style','duration','target_duration','mode','created_at','expires_at')}
                expired.update(status='expired',stage='expired',expired_at=now,message='作品已超过24小时保存期，文件已自动清理。',sources=[],version=0)
                write_json(self.private/'expired'/kind/(identity+'.json'),expired)
                shutil.rmtree(project)
                items[identity]=expired;removed.append(identity)
        # Interrupted uploads may never have written job metadata. Sweep only
        # timestamped user folders, after a full day and outside live records.
        known={Path(record['project']).resolve() for items in (jobs,edits) for record in items.values() if record.get('project')}
        for project in (self.projects/'users').glob('*/*'):
            if not project.is_dir() or project.is_symlink() or project.resolve() in known or self.permanent(project,{}):continue
            if not project.resolve().is_relative_to((self.projects/'users').resolve()):continue
            markers=[path for path in (project/'studio_job.json',project/'editing_job.json') if path.is_file()]
            if markers:
                # Old render-runtime revisions can share an identity. Protect
                # all versions until any active task using that identity ends.
                try:
                    record=json.loads(markers[0].read_text())
                    current=jobs.get(record.get('id')) or edits.get(record.get('id')) or {}
                    if current.get('status') in ACTIVE or record.get('id') in protected or self.permanent(project,record):continue
                    if not record.get('expires_at') or record['expires_at']>now:continue
                except (OSError,ValueError):continue
            elif now-project.stat().st_mtime<TTL:continue
            shutil.rmtree(project)
        # Empty timestamp folders can be removed; the shared public sample tree is never visited.
        for date in (self.projects/'users').glob('*'):
            if date.is_dir() and not any(date.iterdir()):date.rmdir()
        return removed
