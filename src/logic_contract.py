"""Finite-model truth/lie proof, shared by planning, animation and acceptance.

No eval, generated Python, or model-supplied answer is trusted. The supported
contracts cover one-actor contradiction puzzles and a constrained four-person
participation puzzle; self-reference and unrestricted implications are rejected.
"""
import hashlib
import itertools
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def compact(text):
    return re.sub(r'[\s，。；：:;、,“”"「」]', '', text)


def evaluate(claim, world, depth=0):
    if depth > 8 or not isinstance(claim, dict) or len(claim) != 1:
        raise ValueError('命题结构无效或嵌套过深')
    op, args = next(iter(claim.items()))
    if op == 'eq':
        if not isinstance(args, list) or len(args) != 2 or args[0] not in world:
            raise ValueError('eq 必须引用已定义的变量和值')
        return world[args[0]] == args[1]
    if op == 'not': return not evaluate(args, world, depth + 1)
    if op in ('and', 'or', 'xor', 'one') and isinstance(args, list) and 2 <= len(args) <= 4:
        values = [evaluate(a, world, depth + 1) for a in args]
        return all(values) if op == 'and' else sum(values)==1 if op in ('xor','one') else any(values)
    raise ValueError('不支持的命题；不能把不能求解的题当成已验证')


def validate_contract(c, evidence):
    if isinstance(c,dict) and c.get('version')==2:
        return validate_boolean_contract(c,evidence)
    if not isinstance(c, dict) or c.get('version') != 1: raise ValueError('需要 version=1 的逻辑契约')
    people = c.get('people')
    if people != ['甲', '乙', '丙', '丁']: raise ValueError('当前真假话可视化支持甲乙丙丁四人')
    variable = c.get('variable', {})
    if set(variable) != {'id', 'label', 'values'} or variable['id'] != 'actor' or not isinstance(variable['label'], str) or not 1 <= len(variable['label']) <= 8:
        raise ValueError('当前支持单个有限取值事实变量 actor')
    values = variable['values']
    if not isinstance(values, list) or not 2 <= len(values) <= 5 or any(not isinstance(v,str) or not 1 <= len(v) <= 8 for v in values) or len(set(values)) != len(values):
        raise ValueError('需要完整、互斥、有限的候选范围')
    if not set(people).issubset(values): raise ValueError('候选范围必须包含四人；题干没排除外人时需加入其他人')
    if not isinstance(c.get('true_count'), int) or isinstance(c['true_count'],bool) or c['true_count'] != 1: raise ValueError('单人矛盾图解当前支持恰好一句真话；其他题型请使用相应证明模板')
    assumptions = c.get('assumptions', [])
    if not assumptions or any(not isinstance(a,str) or compact(a) not in compact(evidence) for a in assumptions): raise ValueError('每个题设条件必须逐字来自输入，不得补充唯一作案者或范围')
    if not re.search(r'(?:恰有一人|只有一人|仅有一人).{0,14}(?:做|捐|作案|偷|负责|拿|打破|损坏)',compact(evidence)):
        raise ValueError('单人枚举模板需要题干明确只有一人做事；否则应分别建模每个人是否参与')
    statements = c.get('statements')
    if not isinstance(statements,list) or len(statements)!=4: raise ValueError('必须保留四句原话')
    def check_refs(node):
        if not isinstance(node,dict) or len(node)!=1:raise ValueError('无效命题')
        op,args=next(iter(node.items()))
        if op=='eq':
            if not isinstance(args,list) or len(args)!=2 or args[0]!='actor' or args[1] not in values:raise ValueError('命题引用了范围外的对象')
        elif op=='not':check_refs(args)
        elif op in ('and','or') and isinstance(args,list):
            for a in args:check_refs(a)
        else:raise ValueError('不支持该命题')
    for i,s in enumerate(statements):
        if s.get('id')!=f's{i+1}' or s.get('speaker')!=people[i]:raise ValueError('人物、语句ID和顺序不可改变')
        if not isinstance(s.get('text'),str) or not 1 <= len(s['text'])<=60 or compact(s['text']) not in compact(evidence):raise ValueError('原话必须逐字来自输入，不能润色题干')
        check_refs(s.get('claim'))
        evaluate(s['claim'],{'actor':values[0]})
    for world in ({'actor':v} for v in values):
        for s in statements:evaluate(s['claim'],world)


def solve(c, evidence):
    validate_contract(c,evidence)
    if c.get('version')==2:return solve_boolean(c,evidence)
    statements=c['statements'];rows=[]
    for value in c['variable']['values']:
        truth=[evaluate(s['claim'],{'actor':value}) for s in statements]
        rows.append({'actor':value,'truth':truth,'true_count':sum(truth),'valid':sum(truth)==c['true_count']})
    pairs=[]
    for a,b in itertools.combinations(range(4),2):
        if all(r['truth'][a]!=r['truth'][b] for r in rows):pairs.append([a,b])
    winners=[r for r in rows if r['valid']]
    if not winners:raise ValueError('题设无解，禁止继续制作错误讲解')
    if len(winners)!=1:raise ValueError('当前题设有多个解，不能声称有唯一答案；请补充题设或使用不唯一题型')
    if not pairs:raise ValueError('未找到必定一真一假的矛盾对；不能强行套用矛盾法')
    answer=winners[0]
    if c.get('expected_actor') and c['expected_actor']!=answer['actor']:raise ValueError('来源答案与程序验算不一致，需人工核查')
    result={'version':1,'contract':c,'evidence_sha256':hashlib.sha256(evidence.encode()).hexdigest(),'rows':rows,'contradiction_pairs':pairs,'answer':answer}
    result['proof_hash']=digest(result)
    return result


def extraction_prompt(evidence):
    return '''你是形式逻辑题干编译器，不是出题者。只抽取输入给定的甲乙丙丁真假话题。禁止编造题设、问题或答案。
也支持version=2的四人参与题：题目没有说只有一人参与时，不得使用version=1。version=2固定variables为a/b/c/d，各自label甲/乙/丙/丁，values=[false,true]，label为参与者。四句statements保留原文与s1-s4。eq:[a,true]表示甲参与。丁引用甲的话时，展开甲的完整命题。另加options:[{id:A,text:甲是罪犯,claim:{eq:[a,true]}},...]按实际选项填写。true_count=2。只支持甲、丁同义且两真两假、选项问哪人必定参与的题型。变量为布尔值，禁止人为假设只有一人作案。or表示至少一人、one/xor表示恰好一人，按原文选择。assumptions逐字摘录人数条件。当前version=1支持：一个事实变量actor，代表唯一做某事的人，四句陈述为该变量的等于/不等于/合取/析取。若原题不支持，返回{"unsupported":"原因"}。
不能把“涉嫌”当成“作案者一定在四人中”；未明确排除外人需加values=其他人。原话里的“我”按说话人解释。assumptions逐字摘录题设，text逐字摘录每个人的话，不包含甲说前缀，不要改写。true_count是说真话人数。
只输出JSON：{"version":1,"people":["甲","乙","丙","丁"],"variable":{"id":"actor","label":"作案者或捐款人等短名","values":["甲","乙","丙","丁"]},"true_count":1,"assumptions":["原文中的明确条件"],"statements":[{"id":"s1","speaker":"甲","text":"原话","claim":{"eq":["actor","乙"]}},{"id":"s2","speaker":"乙","text":"原话","claim":{"not":{"eq":["actor","乙"]}}},{"id":"s3","speaker":"丙","text":"原话","claim":{"eq":["actor","丁"]}},{"id":"s4","speaker":"丁","text":"原话","claim":{"not":{"eq":["actor","甲"]}}}]}
每个claim允许 eq:[变量ID,值]、not:子命题、and:[子命题,...]、or:[子命题,...]；version=2还允许one/xor:[子命题,...]表示恰好一项成立。示例只说明格式，必须按实际原文填写。
输入原文：\n'''+evidence


def describe(claim, label, negate=False):
    op,args=next(iter(claim.items()))
    if op=='not':return describe(args,label,not negate)
    if op=='eq':return label+('不是' if negate else '是')+args[1]
    join='，并且' if (op=='and') != negate else '，或者'
    return join.join(describe(a,label,negate) for a in args)


def lesson_plan(proof):
    if proof.get('version')==2:return boolean_lesson(proof)
    c=proof['contract'];a,b=proof['contradiction_pairs'][0];people=c['people'];answer=proof['answer'];who=c['variable']['label'];winner=answer['actor']
    pair=f'{people[a]}和{people[b]}'
    other=[i for i in range(4) if i not in (a,b)]
    false_names='、'.join(people[i] for i in other)
    # The contradiction consumes one truth only when exactly one truth exists.
    deductions='。'.join(people[i]+'的话取反，得到'+describe(c['statements'][i]['claim'],who,True) for i in other)
    deduction=(f'全题只有一句真话。{pair}已占用这一句，所以{false_names}的话都假。'+deductions+'。先取反，再检验。' if c['true_count']==1 else f'矛盾对已经固定一真一假。全题要求{c["true_count"]}句真话，我们只需在剩下两句话里找{c["true_count"]-1}句真话。')
    truth_names='、'.join(people[i] for i,v in enumerate(answer['truth']) if v)
    lines=[
      ('question','四个人，谁的话是真的？',f'先别急着四选一。题目问谁是{who}。四个人各说了一句话，而且恰好有{c["true_count"]}句真话。先读原话，再找能突破的关系。'),
      ('contradiction','先找矛盾，不急着猜人',f'看{pair}的原话：一个命题和它的否定，必定一真一假。不论实际是谁，这一对都不可能同时真，也不可能同时假。'),
      ('deduction','锁定真假，缩小范围',deduction),
      ('enumerate','带着条件，逐个假设','我们把所有候选都回代。'+ '。'.join(f'假设是{r["actor"]}，真话有{r["true_count"]}句，'+('符合' if r['valid'] else '排除') for r in proof['rows'])+f'。只保留真话数等于{c["true_count"]}的行。'),
      ('verify','回代原话，确认唯一解',f'唯一保留下来的是{winner}。假设{winner}是{who}，四句原话依次为'+ '、'.join('真' if t else '假' for t in answer['truth'])+f'。说真话的是{truth_names}，恰好{c["true_count"]}句，符合题设。'),
      ('recap','记住方法，下次自己做',f'这道题的答案是{winner}。方法记三步：先找矛盾，再用真话总数锁定其他语句，最后假设回代。区分做事的人和说真话的人，验算通过才落答案。'),
    ]
    beats=[]
    for stage,title,narration in lines:
        beats.append({'scene_id':stage,'title':title,'narration':narration,'caption':title,'visual':f'logic_diagram:{stage}，所有人物、语句、真假标记从同一证明数据计算','duration_seconds':[14,16,16,24,18,12][len(beats)],'proof_hash':proof['proof_hash']})
    outline={'topic':'真假话：从矛盾到唯一解','target_audience':'行测初学者','warnings':[], 'proof_hash':proof['proof_hash'], 'sections':[{'id':'section_1','title':'真假话 · 先找矛盾再验算','goal':'用可视化看懂矛盾法与假设检验','key_points':[x[1] for x in lines],'sources':[]}]}
    board={'proof_hash':proof['proof_hash'],'sections':[{'id':'section_1','title':outline['sections'][0]['title'],'beats':beats,'icon_keywords':[]}]}
    return outline,board


def validate_plan_handoff(document, proof, stage):
    if document.get('proof_hash')!=proof['proof_hash']:raise ValueError('逻辑证据版本不一致')
    if stage=='outline':
        if document != lesson_plan(proof)[0]:raise ValueError('大纲与已验证推理绑定；更换题干需新建创作重新求解')
    if stage=='storyboard':
        beats=[b for s in document['sections'] for b in s['beats']]
        expected=lesson_plan(proof)[1]['sections'][0]['beats']
        if len(beats)!=len(expected):raise ValueError('不能删除必要推理步骤')
        for b,e in zip(beats,expected):
            if any(b.get(k)!=e[k] for k in ('scene_id','proof_hash','narration','visual','caption','title')):raise ValueError('分镜语义已改变，需重新求解与编译；不能跳过证据校验')


def validate_boolean_contract(c, evidence):
    """Bounded family: equivalent first/fourth statements, two truths.

    Exhaust all 16 participation worlds; no hidden single-offender premise.
    A second pass varies ambiguous 'one' quantifiers and requires the same
    necessary conclusion. Unsupported proof shapes fail before rendering.
    """
    if c.get('people') != list('甲乙丙丁') or c.get('true_count') != 2:
        raise ValueError('此图解仅支持四人、两真两假且甲丁同义的参与题')
    expected = [{'id':key,'label':p,'values':[False,True]} for key,p in zip('abcd','甲乙丙丁')]
    if c.get('variables') != expected:raise ValueError('参与题必须保留四个独立布尔变量，不能补充只有一人参与')
    assumptions=c.get('assumptions')
    if not isinstance(assumptions,list) or not assumptions or any(not isinstance(a,str) or compact(a) not in compact(evidence) for a in assumptions):raise ValueError('题设必须来自原文')
    ss=c.get('statements')
    if not isinstance(ss,list) or len(ss)!=4:raise ValueError('需要四句原话')
    atoms=[{'eq':[k,True]} for k in 'abcd']
    first={'and':[{'not':atoms[0]},atoms[1]]}
    def equivalent(claim,wanted):
        return all(evaluate(claim,dict(zip('abcd',values)))==evaluate(wanted,dict(zip('abcd',values))) for values in itertools.product((False,True),repeat=4))
    for i,s in enumerate(ss):
        if s.get('speaker')!='甲乙丙丁'[i] or s.get('id')!=f's{i+1}' or not isinstance(s.get('text'),str) or not 1<=len(s['text'])<=60 or compact(s['text']) not in compact(evidence):raise ValueError('人物与原话必须逐字保留')
    if not equivalent(ss[0]['claim'],first) or not equivalent(ss[3]['claim'],first):raise ValueError('此图解仅支持甲丁同义：甲未参与且乙参与')
    for i,keys in ((1,'acd'),(2,'ab')):
        if not any(equivalent(ss[i]['claim'],{op:[{'eq':[k,True]} for k in keys]}) for op in ('or','one')):raise ValueError('超出当前可验证推理模板的命题范围')
    options=c.get('options')
    if not isinstance(options,list) or len(options)!=4:raise ValueError('真题必须保留四个选项')
    for i,o in enumerate(options):
        if o.get('id')!='ABCD'[i] or o.get('claim')!=atoms[i] or not isinstance(o.get('text'),str) or compact(o['text']) not in compact(evidence):raise ValueError('必须保留原文中四个人分别参与的选项')


def solve_boolean(c,evidence):
    def worlds(statements):
        result=[]
        for vals in itertools.product((False,True),repeat=4):
            world=dict(zip('abcd',vals));truth=[evaluate(s['claim'],world) for s in statements]
            result.append({'world':world,'participants':''.join(p for p,v in zip('甲乙丙丁',vals) if v) or '无人','truth':truth,'true_count':sum(truth),'valid':sum(truth)==2})
        return result
    rows=worlds(c['statements']);valid=[r for r in rows if r['valid']]
    if not valid:raise ValueError('题设无解')
    def entailed(rs):return [o['id'] for o in c['options'] if all(evaluate(o['claim'],r['world']) for r in rs)]
    answers=entailed(valid)
    if len(answers)!=1:raise ValueError('不能推出唯一选项')
    if any(r['valid'] and r['truth'][0] for r in rows):raise ValueError('甲丁同真分支并未排除，不能使用此证明')
    if any(r['truth']!=[False,True,True,False] for r in valid):raise ValueError('幸存世界的真假关系不同，需要其他证明模板')
    sensitivity=[]
    for op1,op2 in itertools.product(('or','one'),repeat=2):
        ss=json.loads(json.dumps(c['statements']))
        ss[1]['claim']={op1:[{'eq':[k,True]} for k in 'acd']};ss[2]['claim']={op2:[{'eq':[k,True]} for k in 'ab']}
        survivors=[r for r in worlds(ss) if r['valid']]
        if not survivors or entailed(survivors)!=answers:raise ValueError('“一人”的解释会影响答案，需明确题设')
        sensitivity.append({'quantifiers':[op1,op2],'valid_worlds':len(survivors),'entailed_options':entailed(survivors)})
    answer=next(o for o in c['options'] if o['id']==answers[0])
    result={'version':2,'contract':c,'evidence_sha256':hashlib.sha256(evidence.encode()).hexdigest(),'rows':rows,'equivalent_pair':[0,3],
            'answer':{'option':answer['id'],'text':answer['text'],'actor':'甲','truth':[False,True,True,False],'true_count':2},'valid_worlds':len(valid),'quantifier_sensitivity':sensitivity}
    result['proof_hash']=digest(result)
    return result


def boolean_lesson(proof):
    lines=[
      ('question','真题：哪一人一定参与？','这是一道兵团行测回忆题。四名嫌疑人中，恰好两人说真话。注意，题目没说只有一个人参与，不能自己加条件。我们只判断谁一定参与。'),
      ('contradiction','先找关系：甲、丁同真同假','先看丁：甲说的是事实。所以甲、丁说法相同，要么都真，要么都假。这不是一真一假的矛盾对，不能把方法生搬硬套。'),
      ('deduction','假设都真，找出冲突','假设甲、丁都真。按甲的原话，甲没参与，乙参与。这样丙说的甲乙中一人参与，也是真的。甲、丙、丁至少三句真话，与恰好两句真话冲突。假设不成立。'),
      ('enumerate','排除同真，只剩同假','所以甲、丁都假。两句真话只能是乙、丙。我们穷举四人各参与或不参与的十六种组合，逐句回代，只留下恰好两句真话的情况。所有保留组合里，都有甲。'),
      ('verify','结论：甲参与；不乱加“只有”','由丙为真，甲乙中一人参与。若甲没参与，就只能乙参与，此时甲的话又变成真，与甲为假冲突。所以甲一定参与，选A。注意，这不等于证明只有甲参与。'),
      ('recap','先认关系，再假设，再回代','总结三步：先认清相同还是矛盾关系；再作假设，用真话总数制造冲突；最后回代原话，选择必然成立的结论。不要把谁说真话，和谁参与事件混为一谈。'),
    ]
    beats=[{'scene_id':stage,'title':title,'narration':narration,'caption':title,'visual':f'logic_diagram:{stage}，从16世界证明与分支读取','duration_seconds':weight,'proof_hash':proof['proof_hash']} for (stage,title,narration),weight in zip(lines,[17,17,24,24,24,14])]
    outline={'topic':'真题：从同义关系到假设排除','target_audience':'行测初学者','warnings':['只推出甲必定参与，不附加只有一个作案者'], 'proof_hash':proof['proof_hash'],'sections':[{'id':'section_1','title':'兵团真题 · 同义关系与假设排除','goal':'区分相同与矛盾关系，检验所有参与组合','key_points':[l[1] for l in lines],'sources':[]}]}
    return outline,{'proof_hash':proof['proof_hash'],'sections':[{'id':'section_1','title':outline['sections'][0]['title'],'beats':beats,'icon_keywords':[]}]}
