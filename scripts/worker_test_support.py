"""Signed internal requests for worker integration tests, never bypassing its boundary."""
import base64
import hashlib
import hmac
import json
import time
from fastapi.testclient import TestClient
import httpx

class WorkerClient(TestClient):
    def __init__(self, server, user='a'*32, config=None, role='user'):
        super().__init__(server.app)
        self.server=server
        self.user=user
        self.role=role
        self.personal=config or {'text':{'protocol':'chat_completions','base_url':'https://example.com/v1','model':'test-model','api_key':'test-generation-secret','fallback_models':[]},'vision':{'protocol':'chat_completions','base_url':'https://example.com/v1','model':'test-vision','api_key':'test-review-secret','fallback_models':[]},'vision_inherit':False,'tts':{'provider':'edge','voice':'zh-CN-XiaoxiaoNeural'}}
    def request(self,method,url,*args,**kwargs):
        payload={'user':{'id':self.user,'role':self.role},'config':self.personal,'admin_id':'c'*32,'time':int(time.time())}
        encoded=base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signed_url=httpx.URL(str(url))
        if kwargs.get('params') is not None:signed_url=signed_url.copy_merge_params(kwargs['params'])
        target=signed_url.raw_path.decode('ascii')
        signature=hmac.new((self.server.PRIVATE/'worker.key').read_bytes(),(method+'\n'+target+'\n'+encoded).encode(),hashlib.sha256).hexdigest()
        kwargs['headers']={**(kwargs.get('headers') or {}),'X-Frame-Context':encoded,'X-Frame-Signature':signature}
        return super().request(method,url,*args,**kwargs)
