"""Durable, per-call usage records. Missing upstream usage is explicitly unknown, never zero."""
import json
import os
import time
import uuid
from billing_client import call as billing_call
from pathlib import Path


def as_dict(value):
    if value is None:return None
    if isinstance(value,dict):return value
    if hasattr(value,'model_dump'):return value.model_dump()
    return vars(value)


def record_usage(settings, role, usage=None, response_id=None, actual_model=None, attempt_id=None, extra=None):
    filename=settings.get('usage_file')
    if not filename:return
    raw=as_dict(usage)
    incoming_raw=raw.get('input_tokens',raw.get('prompt_tokens')) if raw is not None else None
    outgoing_raw=raw.get('output_tokens',raw.get('completion_tokens')) if raw is not None else None
    metered=all(isinstance(v,int) and not isinstance(v,bool) and v>=0 for v in (incoming_raw,outgoing_raw))
    event={'id':attempt_id or uuid.uuid4().hex,'created_at':time.time(),'role':role,
           'requested_model':settings.get('model',''),'model':actual_model or settings.get('model',''),
           'response_id':response_id,'metered':metered,'usage':raw,'stage':settings.get('usage_stage',''),'stream':bool(settings.get('stream',False))}
    if metered:
        incoming=int(raw.get('input_tokens',raw.get('prompt_tokens',0)) or 0)
        outgoing=int(raw.get('output_tokens',raw.get('completion_tokens',0)) or 0)
        details=raw.get('input_tokens_details') or raw.get('prompt_tokens_details') or {}
        cached=details.get('cached_tokens',raw.get('prompt_cache_hit_tokens',0)) or 0
        if isinstance(cached,int) and not isinstance(cached,bool) and 0<=cached<=incoming:
            event.update(input_tokens=incoming,output_tokens=outgoing,cached_input_tokens=cached)
        else:
            event['metered']=False
    if extra:event.update(extra)
    path=Path(filename);path.parent.mkdir(parents=True,exist_ok=True)
    data=(json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try:
        if os.write(fd,data)!=len(data):raise OSError('Incomplete usage record')
        os.fsync(fd)
    finally:os.close(fd)
    billing_call(settings,'settle',event)
