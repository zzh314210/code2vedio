"""Template upgrades must not mutate an existing project's runtime on resume."""
import sys,tempfile,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from configuration import load_config
from video_templates import apply_template
from video_project import initialize_project,input_fingerprint
config=apply_template(load_config(),'word_story')
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);initialize_project(root,'一个原创单词故事',config)
 entries=json.loads((root/'code/runtime/extensions.json').read_text());assert {'story_scene','recall_card','review_cards'}<=entries.keys()
 entries['story_scene']['description']='Archived release description'
 (root/'code/runtime/extensions.json').write_text(json.dumps(entries))
 original=input_fingerprint(root)
 initialize_project(root,'一个原创单词故事',config)
 assert input_fingerprint(root)==original,'Resume silently changed runtime snapshot'
 print('PASS: new projects receive complete helpers; archived extension descriptions and runtime remain immutable on resume.')
