"""Small real compatibility probes for the locally authorized fallback models."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config,sanitize_error
from model_gateway import ModelGateway
config=load_config(ROOT/'config.local.json')
output=ROOT/'.tmp/live-model-probes';output.mkdir(parents=True,exist_ok=True)
canvas=Image.new('RGB',(640,360),'#FBF7EE');draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',64)
draw.text((115,135),'18 - 12 = 6',fill='#196CA5',font=font);picture=output/'equation.png';canvas.save(picture)
results=[]
for role in ('text','vision'):
 models=config[role].get('fallback_models',[])
 if role=='vision':models=[config[role]['model'],*models]
 for model in dict.fromkeys(models):
  settings={**config[role],'model':model,'fallback_models':[], 'max_retries':0,'max_tokens':256,
            'timeout':45,'stream':False,'token_parameter':'max_tokens','public_endpoint_only':True,
            'usage_file':str(output/'usage.jsonl')}
  gateway=ModelGateway(settings,role)
  try:
   prompt='计算18减12，只回答一个数字。' if role=='text' else '读取图片中的等式，原样写出等式，不要添加解释。'
   text,usage=gateway.request(prompt,images=[picture] if role=='vision' else None)
   valid=text.strip()=='6' if role=='text' else all(x in text for x in ('18','12','6'))
   results.append({'role':role,'model':model,'ok':valid,'answer':text,'usage':usage})
   print(role,model,'PASS' if valid else 'UNEXPECTED ANSWER',usage,flush=True)
  except Exception as error:
   results.append({'role':role,'model':model,'ok':False,'error_type':type(error).__name__,'detail':sanitize_error(str(error),config)[:700]})
   print(role,model,'FAILED',type(error).__name__,flush=True)
  finally:gateway.client.close()
  (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print('Results stored:',output/'results.json',flush=True)
