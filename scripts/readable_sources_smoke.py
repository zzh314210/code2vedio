"""A displayed search hit must have a readable, user-owned body, not just a snippet."""
import sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from teaching_library import TeachingSources
with tempfile.TemporaryDirectory() as d:
 s=TeachingSources({'library':d+'/a.sqlite3'})
 candidates=[{'url':'https://example.org/'+str(i),'title':str(i)} for i in range(3)]
 def read(url):
  if url.endswith('1'):raise ValueError('unreadable')
  return s.library.put({'url':url,'title':url[-1],'text':'完整正文。'*120})
 with patch.object(s,'search',return_value={'results':candidates}),patch.object(s,'ingest',side_effect=read):
  result=s.search_readable('关键词')
  assert len(result['results'])==2 and result['unreadable_count']==1
  assert all(s.library.get(x['id'])['text']==x['text'] for x in result['results'])
 other=TeachingSources({'library':d+'/b.sqlite3'})
 assert all(not other.library.get(x['id']) for x in result['results'])
 with patch.object(s,'search',side_effect=AssertionError('Cached query called upstream')):
  cached=s.search_readable('关键词');assert cached['cached'] and len(cached['results'])==2
 with s.library.connect() as db:
  db.execute('UPDATE search_cache SET updated_at=?',(time.time()-90000,))
 with patch.object(s,'search',side_effect=TimeoutError('upstream timeout')):
  fallback=s.search_readable('关键词');assert fallback['cached'] and fallback['notice'] and len(fallback['results'])==2
 for platform in ['bing','bilibili','zhihu']:
  try:s.search('复利',platform)
  except ValueError:pass
  else:raise AssertionError('Unreliable provider enabled')
 with patch.object(other,'search',return_value={'results':[{'url':'https://example.org/empty','pageid':1}]}),patch('encyclopedia_search.article',side_effect=ValueError('No body')):
  try:other.search_readable('空正文')
  except RuntimeError:pass
  else:raise AssertionError('Unusable search presented as a successful empty result')
print('PASS: readable bodies, isolated library, exact cache, stale-cache recovery, unusable search fails clearly, retired providers rejected.')
