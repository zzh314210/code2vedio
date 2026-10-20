"""One durable consumer shared by production/preview, fair turns per account.

Only metadata is shared. Task arguments (including model keys) are encrypted
with each worker's own key. There is no executable serialization or eval.
"""
import base64
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import sqlite3
import threading
import time

from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import BaseModel

LIVE_SECONDS = 60
MAX_USER_WAITING = 5
MAX_WAITING = 30


def resource_status():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        name, value = line.split(':', 1)
        values[name] = int(value.strip().split()[0])
    group = Path(os.getenv('C2V_RESOURCE_CGROUP', '/sys/fs/cgroup/code2vedio.slice'))
    def number(name, default=0):
        try:
            value = (group/name).read_text().strip()
            return int(value) if value != 'max' else default
        except (OSError, ValueError):
            return default
    limit = number('memory.max', 2*1024**3)
    used = number('memory.current')
    try:
        stats=dict(line.split() for line in (group/'memory.stat').read_text().splitlines())
        reclaimable=int(stats.get('inactive_file',0))
    except (OSError,ValueError):reclaimable=0
    minimum = int(os.getenv('C2V_QUEUE_MIN_AVAILABLE_MB', '768'))
    available = values.get('MemAvailable', 0)//1024
    return {'available_mb': available, 'memory_mb': round(used/1024**2),
            'memory_limit_mb': round(limit/1024**2), 'swap_mb': round(number('memory.swap.current')/1024**2),
            'swap_limit_mb': round(number('memory.swap.max', 4*1024**3)/1024**2),
            'cpu_limit': 2.5, 'minimum_available_mb': minimum,
            'ready': available >= minimum and limit-max(0,used-reclaimable) >= min(minimum, 512)*1024**2}


def encode(value):
    if isinstance(value, Path):return ['path', str(value)]
    if isinstance(value, BaseModel):return ['model', type(value).__name__, encode(value.model_dump())]
    if isinstance(value, dict):return ['dict', [[k, encode(v)] for k, v in value.items()]]
    if isinstance(value, (list, tuple)):return ['list', [encode(v) for v in value]]
    if value is None or isinstance(value, (str, int, float, bool)):return ['value', value]
    raise TypeError('Unsupported queue argument')


def decode(value, models):
    kind, *payload = value
    if kind == 'value':return payload[0]
    if kind == 'path':return Path(payload[0])
    if kind == 'list':return [decode(v, models) for v in payload[0]]
    if kind == 'dict':return {k: decode(v, models) for k, v in payload[0]}
    if kind == 'model':return models[payload[0]](**decode(payload[1], models))
    raise ValueError('Invalid queue argument')


class ProductionQueue:
    def __init__(self, directory, namespace, key, handlers, models, describe, on_state,
                 resources=resource_status, interval=2, dispatch_lock=None):
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory/'queue.sqlite3'
        self.namespace, self.handlers, self.models = namespace, handlers, models
        self.describe, self.on_state, self.resources = describe, on_state, resources
        derived = hmac.new(key, b'code2video-production-queue-v1', hashlib.sha256).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(derived))
        self.interval = interval; self.stopping = threading.Event()
        self.dispatch_lock = dispatch_lock if dispatch_lock is not None else threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='video-consumer')
        self.future = None; self.thread = None
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT NOT NULL,
                    identity TEXT NOT NULL, operation TEXT NOT NULL, owner TEXT NOT NULL,
                    title TEXT NOT NULL, kind TEXT NOT NULL, state TEXT NOT NULL,
                    payload BLOB, metadata TEXT NOT NULL, created REAL NOT NULL,
                    started REAL, updated REAL NOT NULL, stage TEXT NOT NULL,
                    estimate_low REAL NOT NULL, estimate_high REAL NOT NULL,
                    UNIQUE(namespace,identity));
                CREATE INDEX IF NOT EXISTS tasks_state_order ON tasks(state,seq);
                CREATE INDEX IF NOT EXISTS tasks_owner_state ON tasks(namespace,owner,state);
                CREATE TABLE IF NOT EXISTS workers(namespace TEXT PRIMARY KEY, heartbeat REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS turns(owner TEXT PRIMARY KEY, served REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,namespace TEXT,actor TEXT,action TEXT,detail TEXT,created REAL);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()

    def start(self):
        with self.connection() as db:
            # Running work may have spent money before interruption. Never replay
            # it automatically. Queued work has made no model calls and can resume.
            interrupted = db.execute("SELECT * FROM tasks WHERE namespace=? AND state='running'", (self.namespace,)).fetchall()
            db.execute("UPDATE tasks SET state='interrupted',payload=NULL WHERE namespace=? AND state='running'", (self.namespace,))
            db.execute('INSERT OR REPLACE INTO workers VALUES(?,?)', (self.namespace, time.time()))
        for row in interrupted:self.on_state(dict(row), 'interrupted')
        self.thread = threading.Thread(target=self.loop, name='queue-scheduler', daemon=True)
        self.thread.start()

    def ensure_capacity(self, owner):
        with self.connection() as db:self._capacity(db, owner)

    def _capacity(self, db, owner):
        if db.execute("SELECT count(*) FROM tasks WHERE state='queued' AND namespace=? AND owner=?", (self.namespace, owner)).fetchone()[0] >= MAX_USER_WAITING:
            raise HTTPException(429, f'你已有 {MAX_USER_WAITING} 条任务在等待，请等一条完成或取消后再提交。')
        if db.execute("SELECT count(*) FROM tasks WHERE state='queued'").fetchone()[0] >= MAX_WAITING:
            raise HTTPException(429, '制作队列暂时已满，请稍后再提交。')

    def submit(self, function, *args):
        with self.dispatch_lock:
            return self._submit(function,*args)

    def _submit(self, function, *args):
        operation = next((key for key, handler in self.handlers.items() if handler == function), None)
        if not operation:raise ValueError('Unregistered queue operation')
        identity = str(args[0]) + (':advice' if operation == 'advice' else '')
        meta = self.describe(operation, args)
        low, high = meta.pop('estimate', [6, 15])
        now = time.time()
        encrypted = self.cipher.encrypt(json.dumps(encode(args), ensure_ascii=False, allow_nan=False).encode())
        old = None
        try:
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                old = db.execute('SELECT state FROM tasks WHERE namespace=? AND identity=?', (self.namespace, identity)).fetchone()
                if old and old['state'] in ('queued', 'running'):
                    raise HTTPException(409, '这条任务已在队列中，请勿重复提交。')
                self._capacity(db, meta['owner'])
                db.execute('DELETE FROM tasks WHERE namespace=? AND identity=?', (self.namespace, identity))
                db.execute('''INSERT INTO tasks(namespace,identity,operation,owner,title,kind,state,payload,metadata,created,updated,stage,estimate_low,estimate_high)
                       VALUES(?,?,?,?,?,?,'queued',?,?,?,?,?,?,?)''',
                       (self.namespace, identity, operation, meta['owner'], meta['title'], meta['kind'], encrypted,
                        json.dumps(meta,ensure_ascii=False), now, now, meta.get('stage','prepare'), low, high))
                row = dict(db.execute('SELECT * FROM tasks WHERE namespace=? AND identity=?', (self.namespace, identity)).fetchone())
        except (HTTPException, sqlite3.Error, OSError):
            # Admission can fail after upload or when another environment fills
            # the queue. Never leave a job looking queued with no durable task.
            if not old or old['state'] not in ('queued', 'running'):
                self.on_state({'identity':identity,'operation':operation,'metadata':json.dumps(meta),'created':now}, 'rejected')
            raise
        self.on_state(row, 'queued')
        return row['seq']

    def has_pending(self, identity):
        with self.connection() as db:
            return bool(db.execute("SELECT 1 FROM tasks WHERE namespace=? AND identity=? AND state IN ('queued','running')", (self.namespace,identity)).fetchone())

    def progress(self, identity, stage):
        with self.connection() as db:
            db.execute("UPDATE tasks SET stage=?,updated=? WHERE namespace=? AND identity=? AND state='running'", (stage,time.time(),self.namespace,identity))

    def _ordered(self, db, live_only=False):
        rows = [dict(row) for row in db.execute("SELECT * FROM tasks WHERE state='queued' ORDER BY seq")]
        if live_only:
            live = {row['namespace'] for row in db.execute('SELECT namespace FROM workers WHERE heartbeat>?', (time.time()-LIVE_SECONDS,))}
            rows = [row for row in rows if row['namespace'] in live]
        turns = {row['owner']:row['served'] for row in db.execute('SELECT * FROM turns')}
        groups = defaultdict(deque)
        for row in rows:groups[row['namespace']+':'+row['owner']].append(row)
        owners = sorted(groups,key=lambda key:(turns.get(key,0),groups[key][0]['seq']))
        ordered=[]
        while any(groups.values()):
            for owner in owners:
                if groups[owner]:ordered.append(groups[owner].popleft())
        # Admin reorder applies to the pending snapshot in that environment.
        # New users still get the slots produced by the fair scheduler.
        for setting in db.execute("SELECT name,value FROM settings WHERE name LIKE 'order:%'"):
            order=json.loads(setting['value']); rank={seq:i for i,seq in enumerate(order)}
            indices=[i for i,row in enumerate(ordered) if row['seq'] in rank]
            overrides=sorted((ordered[i] for i in indices),key=lambda row:rank[row['seq']])
            for i,row in zip(indices,overrides):ordered[i]=row
        return ordered

    def _claim(self):
        with self.dispatch_lock:
            return self._claim_locked()

    def _claim_locked(self):
        resources=self.resources()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO workers VALUES(?,?)',(self.namespace,time.time()))
            if db.execute("SELECT 1 FROM tasks WHERE state='running'").fetchone():return None
            ordered=self._ordered(db,live_only=True)
            if not ordered or ordered[0]['namespace']!=self.namespace or not resources['ready']:return None
            row=ordered[0]
            db.execute("UPDATE tasks SET state='running',started=?,updated=? WHERE seq=?",(time.time(),time.time(),row['seq']))
            db.execute('INSERT OR REPLACE INTO turns VALUES(?,?)',(self.namespace+':'+row['owner'],time.time()))
            return row

    def execute(self,row):
        try:
            arguments=decode(json.loads(self.cipher.decrypt(row['payload'])),self.models)
            self.on_state(row,'running')
            self.handlers[row['operation']](*arguments)
        except BaseException:
            # Details from model requests must never leak through scheduler logs.
            self.on_state(row,'failed')
        finally:
            with self.connection() as db:db.execute("UPDATE tasks SET state='done',payload=NULL,updated=? WHERE seq=?",(time.time(),row['seq']))

    def loop(self):
        while not self.stopping.is_set():
            try:
                with self.connection() as db:
                    db.execute('INSERT OR REPLACE INTO workers VALUES(?,?)',(self.namespace,time.time()))
                    # Only release a crashed consumer after its heartbeat expires.
                    db.execute("UPDATE tasks SET state='interrupted',payload=NULL WHERE state='running' AND namespace IN (SELECT namespace FROM workers WHERE heartbeat<?)", (time.time()-LIVE_SECONDS,))
                if self.future is None or self.future.done():
                    row=self._claim()
                    if row:self.future=self.pool.submit(self.execute,row)
            except (OSError,sqlite3.Error):pass
            self.stopping.wait(self.interval)

    def remaining(self,row):
        low,high=row['estimate_low'],row['estimate_high']
        if row['state']=='running':
            elapsed=max(0,(time.time()-(row['started'] or time.time()))/60)
            low=max(1,low-elapsed);high=max(2,high-elapsed)
        return [math.ceil(low),math.ceil(high)]

    def snapshot(self,identity):
        with self.connection() as db:
            row=db.execute('SELECT * FROM tasks WHERE namespace=? AND identity=?',(self.namespace,identity)).fetchone()
            if not row or row['state'] not in ('running','queued'):return None
            active=db.execute("SELECT * FROM tasks WHERE state='running'").fetchone()
            ordered=self._ordered(db)
        position=next((i+1 for i,item in enumerate(ordered) if item['seq']==row['seq']),0)
        ahead=([dict(active)] if active and active['seq']!=row['seq'] else [])+ordered[:max(0,position-1)]
        wait=[sum(self.remaining(item)[i] for item in ahead) for i in (0,1)]
        memory_wait=not active and not self.resources()['ready']
        return {'state':row['state'],'position':position,'ahead':len(ahead),'waiting':len(ordered),
                'wait_minutes':None if memory_wait else wait,'remaining_minutes':self.remaining(row),
                'waiting_for':'memory' if memory_wait else 'turn','active_stage':active['stage'] if active else None,
                'queued_at':row['created'],'concurrency':1}

    def _version(self, rows):
        return hashlib.sha256(json.dumps([(row['seq'],row['state']) for row in rows]).encode()).hexdigest()

    def admin_snapshot(self):
        with self.connection() as db:
            ordered=self._ordered(db); own=[row for row in ordered if row['namespace']==self.namespace]
            running=[dict(row) for row in db.execute("SELECT * FROM tasks WHERE state='running' AND namespace=?",(self.namespace,))]
            audit=[dict(row) for row in db.execute('SELECT actor,action,detail,created FROM audit WHERE namespace=? ORDER BY id DESC LIMIT 15',(self.namespace,))]
            override=db.execute('SELECT value FROM settings WHERE name=?',('order:'+self.namespace,)).fetchone()
            other_running=bool(db.execute("SELECT 1 FROM tasks WHERE state='running' AND namespace!=?",(self.namespace,)).fetchone())
        def public(row):
            return {key:row[key] for key in ('seq','identity','owner','title','kind','state','created','started','stage')} | {'estimate_minutes':self.remaining(row)}
        return {'running':[public(row) for row in running],'waiting':[public(row) for row in own],
                'version':self._version(own),'manual_order':bool(override and json.loads(override['value'])),
                'other_environment_running':other_running,
                'resources':self.resources(),'concurrency':1,'user_waiting_limit':MAX_USER_WAITING,'audit':audit}

    def reorder(self, order, version, actor):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            own=[row for row in self._ordered(db) if row['namespace']==self.namespace]
            if version!=self._version(own):raise HTTPException(409,'队列已变化，请刷新后再调整。')
            if order and (len(order)!=len(own) or set(order)!={row['seq'] for row in own}):raise HTTPException(422,'请提交当前待处理任务的完整顺序。')
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('order:'+self.namespace,json.dumps(order)))
            db.execute('INSERT INTO audit(namespace,actor,action,detail,created) VALUES(?,?,?,?,?)',(self.namespace,actor,'reorder' if order else 'fair',json.dumps(order),time.time()))
        return self.admin_snapshot()

    def cancel(self,seq,actor,owner=None):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM tasks WHERE seq=? AND namespace=?',(seq,self.namespace)).fetchone()
            if not row or (owner and row['owner']!=owner):raise HTTPException(404,'排队任务不存在。')
            if row['state']!='queued':raise HTTPException(409,'任务已经开始处理或离开队列，无法取消排队。')
            db.execute("UPDATE tasks SET state='cancelled',payload=NULL,updated=? WHERE seq=?",(time.time(),seq))
            db.execute('INSERT INTO audit(namespace,actor,action,detail,created) VALUES(?,?,?,?,?)',(self.namespace,actor,'cancel',json.dumps({'seq':seq,'identity':row['identity']}),time.time()))
        self.on_state(dict(row),'cancelled')
        return {'ok':True}

    def cancel_identity(self,identity,owner):
        with self.connection() as db:
            row=db.execute('SELECT seq FROM tasks WHERE namespace=? AND identity=?',(self.namespace,identity)).fetchone()
        if not row:raise HTTPException(404,'排队任务不存在。')
        return self.cancel(row['seq'],owner,owner)

    def shutdown(self,wait=False):
        self.stopping.set()
        if self.thread:self.thread.join(timeout=5)
        self.pool.shutdown(wait=wait)
