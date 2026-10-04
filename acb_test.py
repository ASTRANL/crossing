#!/usr/bin/env python3
"""Checks ACB-1 on a throwaway database. Exit 0 only when every check holds."""
import json, os, sys, tempfile
os.environ['ACX_DB'] = os.path.join(tempfile.mkdtemp(), 't.db')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acx, acb
fail = []
def ok(cond, what):
    if not cond: fail.append(what)
clock = [1_800_000_000.0]
acx._now = lambda: clock[0]
# a one line goal is accepted and judged VAGUE or ASKABLE, never CLEAR
out, err, st = acb.create({'goal': 'Improve our landing page somehow'}, 'o1')
ok(out and out['clarity']['verdict'] == 'VAGUE', 'vague goal must be VAGUE: %s' % (out and out['clarity']['verdict']))
ok(out and len(out['clarity']['questions']) == 3, 'three questions')
ok(out and out['clarity']['score'] == 10, 'vague goal halves its weight: %s' % (out and out['clarity']['score']))
bid, tok = out['brief'], out['token']
# no goal, short goal, bad numbers are refused
ok(acb.create({}, 'o1')[2] == 400, 'no goal refused')
ok(acb.create({'goal': 'do it'}, 'o1')[2] == 400, 'short goal refused')
ok(acb.create({'goal': 'Translate the README into Dutch', 'reward_usd': '-1'}, 'o1')[2] == 400, 'negative reward refused')
ok(acb.create({'goal': 'Translate the README into Dutch', 'expires_at': '2020-01-01'}, 'o1')[2] == 400, 'past expiry refused')
# wrong token cannot change; right token makes version 2 and a new leaf
ok(acb.update(bid, 'nope', {'acceptance': 'x'})[2] == 403, 'wrong token refused')
out2, err, st = acb.update(bid, tok, {'goal': 'The landing page loads in under 2 seconds on a phone', 'acceptance': 'Lighthouse mobile performance 90 or more on https://example.org',
    'target': 'https://example.org and repo example/site', 'boundaries': 'do not change copy or prices', 'output': 'a pull request', 'evaluator': 'the principal',
    'reward_usd': 5, 'expires_at': '3d', 'if_unclear': 'ask here', 'spend_cap_usd': 0, 'inputs': 'current score is 54'})
ok(out2 and out2['version'] == 2 and out2['clarity']['verdict'] == 'CLEAR' and out2['clarity']['score'] == 100, 'full card is CLEAR 100: %s' % (out2 and out2['clarity']))
ok(out2 and out2['card_sha256'] != out['card_sha256'], 'hash changes with the card')
p, e = acx.proof(out2['log_seq'])
ok(p and p['entry']['kind'] == 'brief' and p['entry']['body']['card_sha256'] == out2['card_sha256'] and p['entry']['body']['version'] == 2, 'leaf carries the card hash')
ok(p['entry']['body'].get('prev_card_sha256') == out['card_sha256'], 'version leaf carries the hash of the version before it')
ok(out2['version_log_seq'] == out2['log_seq'] and out2['defaults_in_force']['spend_cap_usd'] == 0 and out2['reference']['version'] == 2, 'receipt, defaults and reference in the view')
nb = acb.create({'goal': 'The landing page loads in under 2 seconds on a phone', 'acceptance': 'Lighthouse mobile 90 or more', 'target': 'https://example.org', 'output': 'a pull request',
                 'evaluator': 'me', 'reward_usd': 5, 'expires_at': '3d', 'if_unclear': 'ask here', 'spend_cap_usd': 0, 'inputs': 'score is 54'}, 'o9')[0]
ok(nb['clarity']['score'] == 90 and nb['clarity']['verdict'] != 'CLEAR', 'a card without boundaries is never CLEAR: %s' % nb['clarity']['verdict'])
er = acb.update(nb['brief'], nb['token'], {'erase': 'yes'})[0]
ok(er and er['status'] == 'closed' and er['card'].get('erased') and 'Lighthouse' not in json.dumps(er), 'erase removes the text')
# questions: asked once, deduplicated, capped per address, answered by the principal only
q1 = acb.ask(bid, 'agent-a', 'Which page exactly, the home page or pricing?', 'oa')[0]
q1b = acb.ask(bid, 'agent-b', 'which page exactly, the home page or pricing?', 'ob')[0]
ok(q1 and q1b and q1b.get('already_asked') and q1b['id'] == q1['id'], 'same question is not asked twice')
acb.ask(bid, 'agent-a', 'May I add a CDN in front?', 'oa'); acb.ask(bid, 'agent-a', 'Is image compression allowed?', 'oa')
ok(acb.ask(bid, 'agent-a', 'A fourth question from the same address?', 'oa')[2] == 429, 'three questions per address')
a = acb.update(bid, tok, {'answer_to': q1['id'], 'answer': 'The home page only.'})[0]
ok(a and [x for x in a['questions_asked'] if x['id'] == q1['id']][0]['answer'] == 'The home page only.', 'answer is stored')
ok(a['version'] == 2, 'an answer does not change the card version')
# the light reads the brief: slots and reward come from the card; closing turns it red
v = acb.venue(bid)
ok(v and v['state'] == 'open' and v['reward_usd'] == 5 and v['slots'] == 1, 'venue facts from the card')
lk, _ = acx.look('brief:' + bid, 'agent-a', effort_usd=1.0, venue=v)
ok(lk['signal'] == 'GREEN' and lk['worth']['reward_usd'] == 5, 'look uses the card reward: %s' % lk['signal'])
c1 = acx.claim('brief:' + bid, 'agent-a', slots=v['slots'])[0]
c2 = acx.claim('brief:' + bid, 'agent-b', slots=v['slots'])[0]
ok(c1['ok'] and c2.get('full'), 'one slot lets one agent in')
ok(acx.claim('brief:' + bid, 'agent-z', mode='once')[2] == 400, 'once is refused on a brief key')
cl = acb.update(bid, tok, {'close': 'done'})[0]
ok(cl['status'] == 'closed' and cl['for_the_agent'] is None, 'closed brief gives no next calls')
lk2, _ = acx.look('brief:' + bid, 'agent-c', venue=acb.venue(bid))
ok(lk2['signal'] == 'RED', 'closed brief is RED')
ok(acb.ask(bid, 'agent-c', 'Is this still open for work?', 'oc')[2] == 409, 'no questions on a closed brief')
ok(acb.update(bid, tok, {'goal': 'another goal entirely here'})[2] == 409, 'closed brief cannot change')
# expiry
b3 = acb.create({'goal': 'Count the open issues in repo example/site', 'expires_at': '2h'}, 'o3')[0]
clock[0] += 3 * 3600
ok(acb.read(b3['brief'])[0]['status'] == 'expired' and acb.venue(b3['brief'])['state'] == 'closed', 'expired brief is closed for the light')
# lint
l, _ = acb.lint('Make our docs better please')
ok(l['verdict'] == 'SIGNALS_FEW' and len(l['ask_before_you_start']) == 3, 'vague text has few signals: %s' % l['verdict'])
l2, _ = acb.lint('Fix the failing test in https://github.com/example/site/issues/12. Done when `pytest tests/test_api.py` passes. Do not change the public API. Submit a pull request. Bounty $20, deadline 2026-10-12. The maintainer will review. Ask in the issue if unclear. No expenses. See the attached log.')
ok(l2['verdict'] == 'SIGNALS_COMPLETE' and l2['score'] >= 90, 'full text has all signals: %s %s' % (l2['verdict'], l2['score']))
ok(acb.lint('tests a.py only json review free deadline ask budget attached')[0]['verdict'] == 'NOT_JUDGED', 'a bag of keywords is not judged')
ok(acb.lint('https://example.invalid/tests/only/json/review/free/deadline/ask/budget/attached https://example.invalid/a.py')[0]['verdict'] == 'NOT_JUDGED', 'links alone are not judged')
neg = acb.lint('No tests needed; no deadline; no budget; no review. Return json for a.py only, given 2; unpaid; ask nothing.')[0]
ok('acceptance' not in neg['seems_to_say'] and 'evaluator' not in neg['seems_to_say'] and neg['verdict'] != 'SIGNALS_COMPLETE', 'negated acceptance and review are not counted: %s' % sorted(neg['seems_to_say']))
ok(acb.lint('Devuelve \u00fanicamente la suma de dos y dos, por favor, sin nada m\u00e1s.')[0]['verdict'] == 'NOT_JUDGED', 'non English text is not judged')
long = acb.lint('Fix the failing test in the repository. Done when pytest passes. ' + 'x' * 9000 + ' Acceptance is withdrawn.')[0]
ok(any('first 8000' in n for n in long['notes']), 'a cut text says that it was cut')
ok(acb.create({'goal': 'Count the issues. ' + 'y' * 600}, 'o1')[2] == 400, 'an oversized goal is refused')
ok(acb.create({'goal': 'Count the open issues in the repository', 'expires_at': '99999999999'}, 'o1')[2] == 400, 'an expiry beyond a year is refused')
# one address is one voice on the trail
for i in range(3):
    cc = acx.claim('poison-key', 'p-%d' % i, origin='attacker')[0]
    acx.release(cc['lease'], cc['token'], 'failed', 'x', 'invented', 'attacker')
lkp, _ = acx.look('poison-key', 'honest')
ok(lkp['signal'] != 'RED' and lkp['trail']['failure'] <= 1.0, 'one address cannot turn a key RED alone: %s %s' % (lkp['signal'], lkp['trail']['failure']))
c2 = acx.claim('poison-key', 'q-1', origin='second')[0]
m2 = acx.release(c2['lease'], c2['token'], 'failed', 'x', 'https://example.org/proof-of-failure', 'second')[0]
ok(m2['mark']['evidence_counted'] is True and acx.mark('poison-key', 'zz', 'failed', evidence='just words', origin='third')[0]['evidence_counted'] is False, 'evidence must have the form of a link or a hash')
ok(acb.lint('hi')[1] is not None, 'empty text refused')
# per address ceiling
for i in range(acb.PER_ORIGIN_DAY + 1):
    r = acb.create({'goal': 'Count the open issues in repo number %d' % i}, 'flood')
ok(r[2] == 429, 'ceiling on briefs per address')
print(json.dumps({'checks_failed': fail, 'ok': not fail}))
sys.exit(1 if fail else 0)
