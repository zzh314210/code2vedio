"""Authenticated, fail-closed communication with the Go credit ledger."""
import hashlib
import hmac
import json
import time
from pathlib import Path
import httpx

class BillingError(RuntimeError):pass

def call(settings,operation,payload):
    if settings.get('platform_billing') is False:return {'billing':False}
    context=settings.get('billing_context')
    if not context:return {'billing':False}
    directory=Path(context['private'])
    if operation=='authorize':
        path=Path(settings.get('usage_file',''))
        if path.is_file():
            for line in path.read_text().splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                call(settings,'settle',event)
    payload={**payload,'user_id':context['user_id'],'job_id':context['job_id']}
    raw=json.dumps(payload,separators=(',',':')).encode()
    route='/internal/billing/'+operation;stamp=str(int(time.time()))
    signature=hmac.new((directory/'worker.key').read_bytes(),route.encode()+b'\n'+stamp.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    transport=httpx.HTTPTransport(uds=str(directory/'api.sock'))
    try:
        with httpx.Client(transport=transport,timeout=15) as client:
            response=client.post('http://internal'+route,content=raw,headers={'X-Frame-Time':stamp,'X-Frame-Signature':signature,'Content-Type':'application/json'})
            if response.status_code!=200:raise BillingError(response.json().get('detail','计费服务暂不可用。'))
            return response.json()
    except BillingError:raise
    except Exception as error:raise BillingError('计费服务暂不可用，已暂停模型调用，请稍后继续。') from error
