"""Signed internal requests for worker integration tests, never bypassing its boundary."""
import base64
import hashlib
import hmac
import json
import time
from fastapi.testclient import TestClient

class WorkerClient(TestClient):
    def __init__(self, server, user='a'*32, config=None):
        super().__init__(server.app)
        self.server=server
        self.user=user
        self.personal=config or {'text':{'protocol':'chat_completions','base_url':'https://example.com/v1','model':'test-model','api_key':'test-generation-secret','fallback_models':[]},'vision':{'protocol':'chat_completions','base_url':'https://example.com/v1','model':'test-vision','api_key':'test-review-secret','fallback_models':[]},'vision_inherit':False,'tts':{'provider':'edge','voice':'zh-CN-XiaoxiaoNeural'}}
    def request(self,method,url,*args,**kwargs):
        payload={'user':{'id':self.user},'config':self.personal,'admin_id':'c'*32,'time':int(time.time())}
        encoded=base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        signature=hmac.new((self.server.PRIVATE/'worker.key').read_bytes(),(method+'\n'+str(url)+'\n'+encoded).encode(),hashlib.sha256).hexdigest()
        kwargs['headers']={**(kwargs.get('headers') or {}),'X-Frame-Context':encoded,'X-Frame-Signature':signature}
        return super().request(method,url,*args,**kwargs)
