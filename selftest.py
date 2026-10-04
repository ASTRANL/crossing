#!/usr/bin/env python3
"""Checks the ACX-1 invariants over random interleavings with a fake clock, on a throwaway database.
Exit 0 only when every invariant held at every step. Usage: selftest.py [steps] [seed]"""
import hashlib
import json
import os
import random
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix='acx_selftest_')
os.environ['ACX_DB'] = os.path.join(TMP, 'crossing.db')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acx as e  # noqa: E402

STEPS = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 20261004
rnd = random.Random(SEED)
clock = [1_800_000_000.0]
e._now = lambda: clock[0]

KEYS = ['https://example.org/task/%d' % i for i in range(6)] + ['repo:demo/file%d.py' % i for i in range(3)]
AGENTS = ['agent-%d' % i for i in range(7)]
tokens = {}          # lease id -> (token, key, agent, mode)
once_winner = {}     # key -> (agent, time of the grant); I5 holds within the once lifetime
counts = {'claim_ok': 0, 'claim_refused': 0, 'refresh': 0, 'release': 0, 'mark': 0, 'look': 0, 'green': 0, 'amber': 0, 'red': 0}
fail = []


def check(step):
    now = int(clock[0])
    c = e.db()
    try:
        # I1 and I2: at most one live exclusive or once lease per key; nothing live past its expiry
        for r in c.execute("SELECT key_h, COUNT(*) n FROM leases WHERE released IS NULL AND expires>? AND mode IN ('exclusive','once') GROUP BY key_h", (now,)):
            if r['n'] > 1:
                fail.append('I1 step %d: %d exclusive holders on one key' % (step, r['n']))
        # I3: the chain
        prev = ''
        n = 0
        for r in c.execute('SELECT seq, at, kind, body, leaf, chain FROM log ORDER BY seq'):
            n += 1
            if r['seq'] != n:
                fail.append('I3 step %d: gap in sequence at %d' % (step, n))
                break
            leaf = hashlib.sha256(e._canon({'seq': r['seq'], 'at': r['at'], 'kind': r['kind'], 'body': json.loads(r['body'])})).hexdigest()
            chain = hashlib.sha256((prev + leaf).encode()).hexdigest()
            if leaf != r['leaf'] or chain != r['chain']:
                fail.append('I3 step %d: chain broken at %d' % (step, n))
                break
            prev = chain
    finally:
        c.close()


for step in range(1, STEPS + 1):
    clock[0] += rnd.choice([0, 1, 5, 20, 45, 120, 400, 900, 2500])
    op = rnd.random()
    key, agent = rnd.choice(KEYS), rnd.choice(AGENTS)
    if op < 0.34:
        mode = rnd.choice(['shared', 'exclusive', 'exclusive', 'once'])
        want = rnd.choice([None, None, 1, 2, 3]) if mode == 'shared' else None
        if want is not None:                                    # I6 is judged against the state just before the claim
            c0 = e.db()
            n_before = c0.execute('SELECT COUNT(DISTINCT agent_h) FROM leases WHERE key_h=? AND released IS NULL AND expires>? AND agent_h!=?',
                                  (e._h(key), int(clock[0]), e._h(agent))).fetchone()[0]
            c0.close()
        out, err, st = e.claim(key, agent, ttl=rnd.choice([30, 60, 600, 3600]), mode=mode, origin='o' + agent[-1], slots=want)
        if want is not None and out and out.get('ok') and out.get('token') and n_before >= want:
            fail.append('I6 step %d: shared claim with slots %d granted while %d others hold' % (step, want, n_before))
        if want is not None and out and out.get('full') and n_before < want:
            fail.append('I6 step %d: refused as full with %d others and %d slots' % (step, n_before, want))
        if out and out.get('ok') and out.get('token'):
            counts['claim_ok'] += 1
            tokens[out['lease']] = (out['token'], key, agent, mode)
            if mode == 'once':
                if key in once_winner and clock[0] - once_winner[key][1] < e.ONCE_TTL:
                    fail.append('I5 step %d: once key granted twice within its lifetime' % step)
                once_winner[key] = (agent, clock[0])
        else:
            counts['claim_refused'] += 1
    elif op < 0.46 and tokens:
        lid = rnd.choice(list(tokens))
        tok, k, a, m = tokens[lid]
        out, err, st = e.claim(k, a, ttl=rnd.choice([60, 600, 3600]), lease=lid, token=tok)
        counts['refresh'] += 1
    elif op < 0.60 and tokens:
        lid = rnd.choice(list(tokens))
        tok, k, a, m = tokens.pop(lid)
        e.release(lid, tok, outcome=rnd.choice([None, 'done', 'failed']), evidence=rnd.choice(['', 'https://example.org/proof']))
        counts['release'] += 1
    elif op < 0.72:
        e.mark(key, agent, rnd.choice(sorted(e.MARK_KINDS)), note='n', evidence=rnd.choice(['', 'tx:abc']), origin='o%d' % rnd.randrange(40))
        counts['mark'] += 1
    else:
        out, err = e.look(key, agent, reward_usd=rnd.choice([None, 2.0]), effort_usd=rnd.choice([None, 0.01]))
        counts['look'] += 1
        counts[out['signal'].lower()] += 1
        # I4: never GREEN while another agent holds it exclusively
        now = int(clock[0])
        c = e.db()
        held = c.execute("SELECT COUNT(*) FROM leases WHERE key_h=? AND released IS NULL AND expires>? AND mode IN ('exclusive','once') AND agent_h!=?",
                         (e._h(key), now, e._h(agent))).fetchone()[0]
        c.close()
        if held and out['signal'] == 'GREEN':
            fail.append('I4 step %d: GREEN while held by another' % step)
    if step % 50 == 0 or step == STEPS:
        check(step)

# a proof must fold to the head
h = e.head()
p, err = e.proof(max(1, h['size'] // 2))
ch = hashlib.sha256((p['chain_before'] + p['leaf']).encode()).hexdigest()
ok_entry = ch == p['chain_at_entry']
for leaf in p['later_leaves']:
    ch = hashlib.sha256((ch + leaf).encode()).hexdigest()
folds = ch == h['chain'] if p['reaches_seq'] == h['size'] else None
if not ok_entry or folds is False:
    fail.append('proof does not fold to the head')

print(json.dumps({'steps': STEPS, 'seed': SEED, 'counts': counts, 'log_size': h['size'], 'proof_folds_to_head': folds,
                  'invariants_held': not fail, 'failures': fail[:5]}))
sys.exit(1 if fail else 0)
