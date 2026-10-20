"""Bind the persistent consumer to existing creation, review and editing jobs."""
import json
import os
from pathlib import Path
import threading
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from production_queue import ProductionQueue
from video_project import write_json
from revision_api import FilmRevision


class QueueOrder(BaseModel):
    order:list[int]=Field(max_length=30)
    version:str=Field(min_length=64,max_length=64)


def register_queue(env):
    app=env['app']; router=APIRouter()
    def queue():
        result=env.get('production_queue')
        if not result:raise HTTPException(503,'制作队列尚未启动，请稍后刷新。')
        return result
    def admin():
        user=env['current_user'].get()
        if user.get('role')!='admin':raise HTTPException(403,'需要管理员权限。')
        return user['id']

    @router.get('/api/admin/queue')
    def listing():admin();return queue().admin_snapshot()

    @router.put('/api/admin/queue/order')
    def reorder(value:QueueOrder):return queue().reorder(value.order,value.version,admin())

    @router.delete('/api/admin/queue/{sequence}')
    def cancel(sequence:int):return queue().cancel(sequence,admin())

    @router.post('/api/jobs/{identity}/cancel')
    def cancel_video(identity:str):return queue().cancel_identity(identity,env['current_user'].get()['id'])

    @router.post('/api/edits/{identity}/cancel')
    def cancel_edit(identity:str):return queue().cancel_identity(identity,env['current_user'].get()['id'])

    app.include_router(router)

    def describe(operation,args):
        identity=args[0]
        record=(env['editing_service'].jobs if operation=='edit' else env['jobs'])[identity]
        duration=record.get('duration') or record.get('target_duration',30)
        estimate=[6,15] if duration<=45 else [12,30] if duration<=90 else [18,40] if duration<=120 else [25,55] if duration<=180 else [40,90]
        action=args[-1] if operation=='edit' else ''
        if operation=='advice':estimate=[1,4]
        elif operation=='planning':estimate=[1,5]
        elif operation=='edit':estimate=[2,8] if action=='render' else ([10,30] if sum(s.get('duration',0) for s in record.get('sources',[]))>300 else [3,10])
        elif not record.get('auto_approve') and record.get('stage') in ('outline','storyboard'):
            estimate=[1,4] if record.get('stage')=='outline' else [2,6]
        return {'owner':record['owner_id'],'title':record['prompt'][:100],
                'kind':'edit' if operation=='edit' else 'advice' if operation=='advice' else 'video',
                'project':record.get('project') or str(env['editing_service'].directory(identity)),
                'stage':record.get('stage','prepare'),'action':action,'estimate':estimate}

    def state(row,status):
        identity=row['identity'].removesuffix(':advice')
        metadata=json.loads(row['metadata'])
        operation=row['operation']
        messages={'queued':'已加入制作队列，轮到后自动开始。','running':'已轮到你，正在准备制作。',
                  'cancelled':'已取消排队，未启动的任务不会产生模型费用。',
                  'interrupted':'制作服务曾中断，已保留现有步骤，请检查后重试。',
                  'rejected':'队列暂时已满，未开始制作，请稍后重试。',
                  'failed':'制作未完成，已保留任务，请重试。'}
        if operation=='advice':
            target=Path(metadata['project'])/'revision_advice.json'
            value={'status':'failed' if status in ('cancelled','interrupted','failed','rejected') else status,
                   'message':messages[status],'requested_at':row['created']}
            write_json(target,value)
            if status in ('cancelled','interrupted','failed','rejected'):env['revision_service'].advice_running.discard(identity)
            return
        target_status='failed' if status in ('interrupted','failed','rejected') else status
        if operation=='edit':
            service=env['editing_service']
            if identity not in service.jobs:return
            if status=='running':target_status='analyzing' if metadata['action']=='analyze' else 'rendering'
            service.update(identity,status=target_status,message=messages[status],failed_action=metadata['action'])
        else:
            if identity not in env['jobs']:env['discover']()
            if identity not in env['jobs']:return
            if status=='running' and operation in ('revision','planning'):target_status='revising'
            if status in ('cancelled','rejected') and operation=='planning':target_status='awaiting_review'
            env['update_job'](identity,status=target_status,message=messages[status])

    stop=threading.Event(); maintenance=None

    @app.on_event('startup')
    def start():
        nonlocal maintenance
        if os.getenv('C2V_QUEUE_ENABLED')!='1':return
        env['storage'].migrate()
        env['discover']()
        service=env['editing_service'];service.storage=env['storage']
        # Reload migrated expiry metadata and durable queued editing jobs.
        from storage_lifecycle import records
        for path in records(env['STUDIO_PROJECTS'],'editing_job.json'):
            record=json.loads(path.read_text());record['project']=str(path.parent);service.jobs[record['id']]=record
        for record in env['storage'].expired_records('edit'):service.jobs[record['id']]=record
        directory=Path(os.getenv('C2V_QUEUE_DIR',str(env['ROOT']/'.runtime')))
        namespace=os.getenv('C2V_QUEUE_NAMESPACE','production')
        consumer=ProductionQueue(directory,namespace,(env['PRIVATE']/'worker.key').read_bytes(),
            {'video':env['work'],'revision':env['revision_service'].revision_worker,
             'planning':env['revise_worker'],'advice':env['revision_service'].advice_worker,'edit':service.work},
            {'FilmRevision':FilmRevision,'PlanningRevision':env['PlanningRevision']},describe,state,dispatch_lock=env['lock'])
        env['executor'].shutdown(wait=False)
        env['revision_service'].advice_pool.shutdown(wait=False)
        env['production_queue']=consumer;env['executor']=consumer
        env['revision_service'].advice_pool=consumer;service.executor=consumer;service.queue=consumer
        # discover() deliberately marks orphan running jobs failed. Restore only
        # the pending entries that the durable queue can actually resume.
        with consumer.connection() as db:
            pending=[dict(row) for row in db.execute("SELECT * FROM tasks WHERE namespace=? AND state='queued'",(namespace,))]
        for row in pending:state(row,'queued')
        consumer.start()
        def sweep():
            while not stop.is_set():
                try:
                    with env['lock']:
                        env['storage'].collect(env['jobs'],service.jobs,consumer)
                        env['music_service'].cleanup()
                except (OSError,ValueError):pass
                stop.wait(60)
        maintenance=threading.Thread(target=sweep,name='artifact-cleanup',daemon=True);maintenance.start()

    @app.on_event('shutdown')
    def shutdown():
        stop.set()
        if env.get('production_queue'):env['production_queue'].shutdown(wait=False)
