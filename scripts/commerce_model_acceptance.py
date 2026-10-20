"""Explicit real-model checks for sales conditions; opt-in model consumption."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config
from model_gateway import ModelGateway
from editing import review_commerce
out=ROOT/'.tmp/commerce-acceptance';out.mkdir(exist_ok=True)
config=load_config(ROOT/'config.local.json',overrides={'text':{'model':'kimi-k3','fallback_models':['deepseek-v4.1-flash-1017']}})['text'];config['usage_file']=str(out/'usage.jsonl');gateway=ModelGateway(config)
sources=[{'id':'s1','name':'原创报价条件验收用例，非真实商品广告','transcript':[
 {'start':0,'end':6,'text':'现在介绍A款，五百毫升不锈钢保温杯。'},
 {'start':6,'end':16,'text':'杯盖可以旋紧，杯身有防滑纹理，倒水的时候握稳杯身。'},
 {'start':16,'end':22,'text':'A款今天到手九十九元。'},
 {'start':22,'end':32,'text':'注意，九十九元只适用于新用户，必须先领三十元优惠券，而且每人限买一件。'},
 {'start':32,'end':40,'text':'喜欢A款的朋友，请确认自己符合刚才说的条件，再领券下单。'},
 {'start':40,'end':46,'text':'下面换一个商品，B款三百毫升陶瓷马克杯，没有保温功能。'},
 {'start':46,'end':54,'text':'这款价格四十九元，所有用户都可以买，不需要领券。'}]}]
cases=[('complete',[(0,40)],True),('demonstration_without_offer',[(0,16)],True),('missing_coupon_conditions',[(0,22),(32,40)],False),('cross_product_price',[(0,16),(46,54)],False)]
results=[]
for name,ranges,expected in cases:
 d=out/name;d.mkdir(exist_ok=True)
 plan={'clips':[{'source_id':'s1','start':a,'end':b} for a,b in ranges]}
 result=review_commerce(d,sources,plan,gateway);results.append({'case':name,'expected':expected,'actual':result['passed'],'issues':result['issues']})
 print(name,'PASS' if result['passed']==expected else 'FAIL',flush=True)
(out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
assert all(x['expected']==x['actual'] for x in results),results
print('PASS: complete original offer accepted; missing coupon conditions and mixed-product price rejected by configured real model.')
