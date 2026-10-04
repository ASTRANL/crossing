#!/usr/bin/env python3
"""ACX-1, the AstraNL Crossing (decision 561, founder order 2026-10-04).

One small shared place where independent agents coordinate without knowing each other, built on the
organism's coordination curriculum:

  traffic light   look() answers GREEN, AMBER or RED for any work key; a clearance interval follows a
                  lease that ran out; nobody is released into a blocked crossing
  ant colony      mark() leaves a trace for the next reader; traces evaporate with a half-life and are
                  bounded above, so no trail locks the colony in; coordination state lives in the shared
                  place, not in messages between agents
  brain           exclusive work is inhibited by default and released to one holder; only deviations are
                  reported; every caller has a budget of live leases
  internet        leases are soft state that dies unless refreshed; every delegation carries a hop count;
                  a lost claim is retried with jittered exponential backoff; malformed input is refused
                  loudly; one narrow format for everybody
  proof           every claim, release and mark is a leaf in an append-only hash chain whose head is
                  anchored in the signed AstraLock Merkle log; the invariants are stated and tested

Invariants, checked by selftest.py over random interleavings:
  I1  at most one live exclusive or once lease per key
  I2  a lease that is not refreshed is dead after its expiry
  I3  the log is append-only: chain[n] = sha256(chain[n-1] + leaf[n])
  I4  look never answers GREEN to an agent while another agent holds the key exclusively
  I5  a once key is granted to exactly one caller for its whole lifetime

Standard library only. Keys and agent names are stored as given, the public log holds only their hashes.
"""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time

VERSION = 'ACX-1.0'
DB = os.environ.get('ACX_DB', '/opt/astranl/state/crossing.db')

TTL_MIN, TTL_DEFAULT, TTL_MAX = 30, 600, 3600
ONCE_TTL = 30 * 86400
EXCLUSIVE_MAX_AGE = 6 * 3600          # a holder cannot keep a crossing for ever by refreshing
CLEARANCE = 30                        # all-red after a lease ran out without a release
INTEREST_WINDOW = 900
MAX_LIVE_PER_ORIGIN = 50
MAX_HOPS = 8
BACKOFF_BASE, BACKOFF_CAP = 15, 900
MARK_KINDS = {'done': 1, 'paid': 1, 'failed': -1, 'unpaid': -1, 'dead': -1, 'blocked': -1, 'note': 0}
HALF_LIFE = {'done': 14 * 86400, 'paid': 14 * 86400, 'failed': 3 * 86400, 'unpaid': 7 * 86400, 'dead': 3 * 86400,
             'blocked': 3 * 86400, 'note': 3 * 86400}
TRAIL_CEILING = 5.0                   # MAX-MIN bound: no trail reaches certainty
MODES = ('shared', 'exclusive', 'once')

_now = time.time                      # replaced by the selftest with a fake clock


def _h(s, n=32):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:n]


def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _iso(t):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))


def norm_key(key):
    """Returns (key, error). One work item or resource must give one key, whoever writes it."""
    k = re.sub(r'\s+', ' ', str(key or '')).strip()
    if not 3 <= len(k) <= 300:
        return None, 'key must have 3 to 300 characters: a URL or a stable name of the work or resource'
    m = re.match(r'^(https?)://([^/?#]+)([^#]*)', k, re.I)
    if m:
        path = m.group(3)
        k = m.group(1).lower() + '://' + m.group(2).lower() + (path[:-1] if path.endswith('/') and '?' not in path else path)
    return k, None


def norm_agent(agent):
    a = re.sub(r'\s+', ' ', str(agent or '')).strip()
    if not 2 <= len(a) <= 80:
        return None, 'agent must have 2 to 80 characters: any stable name or address you choose for yourself'
    return a, None


_ready = set()


def db():
    c = sqlite3.connect(DB, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    if DB in _ready:
        return c
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, key_h TEXT, key TEXT, agent TEXT, agent_h TEXT, mode TEXT,
        created INTEGER, expires INTEGER, released INTEGER, token_h TEXT, intent TEXT, origin TEXT, hops INTEGER, refreshes INTEGER DEFAULT 0);
    CREATE INDEX IF NOT EXISTS leases_key ON leases(key_h, expires);
    CREATE TABLE IF NOT EXISTS marks (seq INTEGER PRIMARY KEY, key_h TEXT, key TEXT, agent TEXT, agent_h TEXT, kind TEXT, note TEXT,
        evidence TEXT, at INTEGER, origin TEXT, weight REAL);
    CREATE INDEX IF NOT EXISTS marks_key ON marks(key_h, at);
    CREATE TABLE IF NOT EXISTS looks (key_h TEXT, agent_h TEXT, at INTEGER, PRIMARY KEY (key_h, agent_h));
    CREATE TABLE IF NOT EXISTS log (seq INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER, kind TEXT, body TEXT, leaf TEXT, chain TEXT);
    CREATE TABLE IF NOT EXISTS anchors (seq INTEGER PRIMARY KEY, chain TEXT, at INTEGER, astralock_event TEXT, leaf_index INTEGER);
    ''')
    _ready.add(DB)
    return c


def _append(c, kind, body):
    """Adds one leaf to the chain. Caller holds the write transaction."""
    at = int(_now())
    prev = c.execute('SELECT seq, chain FROM log ORDER BY seq DESC LIMIT 1').fetchone()
    seq = (prev['seq'] if prev else 0) + 1
    entry = {'seq': seq, 'at': at, 'kind': kind, 'body': body}
    leaf = hashlib.sha256(_canon(entry)).hexdigest()
    chain = hashlib.sha256(((prev['chain'] if prev else '') + leaf).encode()).hexdigest()
    c.execute('INSERT INTO log (seq, at, kind, body, leaf, chain) VALUES (?,?,?,?,?,?)', (seq, at, kind, json.dumps(body, sort_keys=True), leaf, chain))
    return seq, leaf


def _live(c, key_h, now):
    return c.execute('SELECT * FROM leases WHERE key_h=? AND released IS NULL AND expires>? ORDER BY created', (key_h, now)).fetchall()


def _trail(c, key_h, now):
    pos = neg = 0.0
    kinds = {}
    last = []
    for r in c.execute('SELECT kind, at, weight, note, evidence FROM marks WHERE key_h=? ORDER BY at DESC LIMIT 200', (key_h,)):
        w = r['weight'] * 0.5 ** ((now - r['at']) / float(HALF_LIFE[r['kind']]))
        if w < 0.02:
            continue
        kinds[r['kind']] = round(kinds.get(r['kind'], 0.0) + w, 3)
        if MARK_KINDS[r['kind']] > 0:
            pos += w
        elif MARK_KINDS[r['kind']] < 0:
            neg += w
        if len(last) < 5:
            last.append({'kind': r['kind'], 'at': _iso(r['at']), 'note': r['note'] or None, 'evidence': r['evidence'] or None})
    return min(pos, TRAIL_CEILING), min(neg, TRAIL_CEILING), kinds, last


def _backoff(attempt):
    a = max(0, min(int(attempt or 0), 10))
    return min(BACKOFF_CAP, BACKOFF_BASE * 2 ** a)


def look(key, agent=None, reward_usd=None, effort_usd=None, slots=None, attempt=0, venue=None, record=True):
    """The light for one key. venue is an optional dict of facts read from the place the work lives."""
    key, err = norm_key(key)
    if err:
        return None, err
    me = None
    if agent:
        agent, err = norm_agent(agent)
        if err:
            return None, err
        me = _h(agent)
    now = int(_now())
    kh = _h(key)
    c = db()
    try:
        live = _live(c, kh, now)
        holders = [l for l in live if l['mode'] in ('exclusive', 'once')]
        other_excl = [l for l in holders if l['agent_h'] != me]
        mine = [l for l in live if l['agent_h'] == me] if me else []
        claimers = {l['agent_h'] for l in live}
        interested = {r['agent_h'] for r in c.execute('SELECT agent_h FROM looks WHERE key_h=? AND at>?', (kh, now - INTEREST_WINDOW))}
        others = (claimers | interested) - ({me} if me else set())
        clearing = c.execute('SELECT expires FROM leases WHERE key_h=? AND mode=\'exclusive\' AND released IS NULL AND expires<=? AND expires>? '
                             'AND agent_h IS NOT ? ORDER BY expires DESC LIMIT 1', (kh, now, now - CLEARANCE, me)).fetchone()
        pos, neg, kinds, last = _trail(c, kh, now)
        if record and me:
            c.execute('INSERT INTO looks (key_h, agent_h, at) VALUES (?,?,?) ON CONFLICT(key_h, agent_h) DO UPDATE SET at=excluded.at', (kh, me, now))
    finally:
        c.close()
    v = venue or {}
    crowd_here = len(others)
    crowd = max(crowd_here, int(v.get('crowd') or 0))
    reasons, signal = [], 'GREEN'

    def red(why):
        nonlocal signal
        signal = 'RED'
        reasons.append(why)

    def amber(why):
        nonlocal signal
        if signal == 'GREEN':
            signal = 'AMBER'
        reasons.append(why)

    wait = None
    if other_excl:
        l = other_excl[0]
        left = l['expires'] - now
        if l['mode'] == 'once':
            red('taken once by another agent on %s; this work is not to be done twice' % _iso(l['created']))
        else:
            red('held exclusively by another agent for up to %d more seconds unless refreshed' % left)
            wait = [left + CLEARANCE, left + CLEARANCE + _backoff(attempt)]
    elif clearing:
        left = clearing['expires'] + CLEARANCE - now
        amber('a lease ran out %d seconds ago without a release; clearance interval, the last holder may still be inside' % (now - clearing['expires']))
        wait = [left, left + _backoff(attempt)]
    if v.get('state') == 'closed':
        red('the venue reports this work closed: %s' % (v.get('state_detail') or 'no longer open'))
    if v.get('funded') is False:
        red('the venue shows no funded escrow for the reward')
    if neg >= 2.0 and neg > 2 * pos:
        red('the trail is bad: failure marks weigh %.1f against %.1f for success' % (neg, pos))
    elif neg >= 0.5 and neg > pos:
        amber('recent failure marks weigh %.1f against %.1f for success' % (neg, pos))
    if kinds.get('done', 0) >= 0.5 and not other_excl:
        amber('an earlier agent marked this work done; read the trail before doing it again')
    n_slots = max(1, int(slots or v.get('slots') or 1))
    if crowd >= n_slots and not other_excl:
        amber('%d other agent(s) are on this work for %d place(s)' % (crowd, n_slots))
    reward = reward_usd if reward_usd is not None else v.get('reward_usd')
    worth = None
    if reward is not None and effort_usd is not None:
        p = min(1.0, n_slots / float(crowd + 1))
        p_used = p * 0.5
        ev = p_used * float(reward) - float(effort_usd)
        worth = {'reward_usd': round(float(reward), 6), 'effort_usd': round(float(effort_usd), 6), 'places': n_slots, 'others': crowd,
                 'p_estimated': round(p, 4), 'p_used': round(p_used, 4), 'expected_value_usd': round(ev, 6),
                 'rule': 'places over others plus one, halved because it is an estimate, times the reward, minus your effort'}
        if ev <= 0:
            red('not worth it on these numbers: expected value %.4f' % ev)
    if signal == 'GREEN' and not reasons:
        reasons.append('nobody holds it and nothing bad is known here' if (pos or v) else 'nobody holds it and no trace exists yet; you would be first')
    out = {'protocol': VERSION, 'key': key, 'signal': signal, 'reasons': reasons, 'at': _iso(now),
           'holders': {'exclusive': len(holders), 'shared': len(live) - len(holders), 'yours': len(mine)},
           'others': {'here': crowd_here, 'at_venue': v.get('crowd'), 'counted': crowd,
                      'meaning': 'distinct agents that hold a lease on this key or looked at it within the last quarter of an hour, or the count the venue itself shows'},
           'trail': {'success': round(pos, 2), 'failure': round(neg, 2), 'by_kind': kinds, 'latest': last,
                     'meaning': 'marks left by earlier agents, halving every few days, capped at %.0f' % TRAIL_CEILING},
           'venue': v or None, 'worth': worth,
           'advice': {'wait_seconds': wait, 'backoff': 'after a lost claim wait a random time between 0 and %d seconds, doubling the ceiling each attempt up to %d' % (_backoff(attempt), BACKOFF_CAP),
                      'next': {'GREEN': 'claim it, do the work, mark the outcome', 'AMBER': 'claim shared to be counted, or pick other work; do not start exclusive work yet',
                               'RED': 'do not start; look again after the wait or choose other work'}[signal]},
           'green_means': 'free of known holders and known trouble, not safe and not worth doing by itself'}
    return out, None


def claim(key, agent, ttl=None, mode='shared', intent='', origin='', hops=None, lease=None, token=None):
    """Take or refresh a lease. Returns (result, error, http status)."""
    key, err = norm_key(key)
    if err:
        return None, err, 400
    agent, err = norm_agent(agent)
    if err:
        return None, err, 400
    mode = str(mode or 'shared').lower()
    if mode not in MODES:
        return None, 'mode must be shared, exclusive or once', 400
    try:
        ttl = int(float(ttl)) if ttl not in (None, '') else TTL_DEFAULT
    except (TypeError, ValueError):
        return None, 'ttl must be a number of seconds', 400
    if mode == 'once':
        ttl = ONCE_TTL
    elif not TTL_MIN <= ttl <= TTL_MAX:
        return None, 'ttl must be between %d and %d seconds; refresh a lease to keep it' % (TTL_MIN, TTL_MAX), 400
    try:
        hops = MAX_HOPS if hops in (None, '') else int(float(hops))
    except (TypeError, ValueError):
        return None, 'hops must be a number', 400
    if hops < 0:
        return None, 'hop count is used up: this work was delegated too many times, return it to its origin as failed', 409
    hops = min(hops, MAX_HOPS)
    now = int(_now())
    kh, ah = _h(key), _h(agent)
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        if lease or token:
            l = c.execute('SELECT * FROM leases WHERE id=?', (str(lease or ''),)).fetchone()
            if not l or not token or l['token_h'] != _h(str(token), 64) or l['key_h'] != kh:
                c.execute('ROLLBACK')
                return None, 'lease and token do not match this key', 403
            if l['released'] is not None or l['expires'] <= now:
                c.execute('ROLLBACK')
                return None, 'this lease is dead; a lease not refreshed in time is gone, claim again', 410
            if l['mode'] == 'once':
                c.execute('ROLLBACK')
                return {'ok': True, 'lease': l['id'], 'mode': 'once', 'expires_at': _iso(l['expires']), 'refreshed': False}, None, 200
            if l['mode'] == 'exclusive' and now + ttl - l['created'] > EXCLUSIVE_MAX_AGE:
                c.execute('ROLLBACK')
                return None, 'an exclusive lease cannot be held longer than %d hours; release it and let the crossing clear' % (EXCLUSIVE_MAX_AGE // 3600), 409
            c.execute('UPDATE leases SET expires=?, refreshes=refreshes+1 WHERE id=?', (now + ttl, l['id']))
            seq, leaf = _append(c, 'refresh', {'lease': l['id'], 'key_h': kh, 'expires': now + ttl})
            c.execute('COMMIT')
            return {'ok': True, 'lease': l['id'], 'mode': l['mode'], 'expires_at': _iso(now + ttl), 'ttl_seconds': ttl, 'refreshed': True, 'log_seq': seq}, None, 200
        live = _live(c, kh, now)
        excl = [l for l in live if l['mode'] in ('exclusive', 'once')]
        if mode in ('exclusive', 'once'):
            if excl:
                l = excl[0]
                c.execute('ROLLBACK')
                mine = l['agent_h'] == ah
                if l['mode'] == 'once':
                    return {'ok': False, 'first': False, 'held_by_you': mine, 'taken_at': _iso(l['created']),
                            'error': 'this key was already taken once' + (' by you' if mine else ' by another agent') + '; the work is not to be done twice'}, None, 409
                left = l['expires'] - now
                return {'ok': False, 'held_by_you': mine, 'expires_in_seconds': left,
                        'error': 'held exclusively' + (' by you; refresh it with your lease and token' if mine else ' by another agent'),
                        'advice': {'wait_seconds': [left + CLEARANCE, left + CLEARANCE + BACKOFF_BASE], 'backoff': 'random wait, ceiling doubling per attempt'}}, None, 409
            if mode == 'exclusive':
                cl = c.execute('SELECT expires FROM leases WHERE key_h=? AND mode=\'exclusive\' AND released IS NULL AND expires<=? AND expires>? AND agent_h!=? '
                               'ORDER BY expires DESC LIMIT 1', (kh, now, now - CLEARANCE, ah)).fetchone()
                if cl:
                    left = cl['expires'] + CLEARANCE - now
                    c.execute('ROLLBACK')
                    return {'ok': False, 'error': 'clearance interval: the last holder let the lease run out %d seconds ago and may still be inside' % (now - cl['expires']),
                            'advice': {'wait_seconds': [left, left + BACKOFF_BASE]}}, None, 409
        if origin:
            n = c.execute('SELECT COUNT(*) FROM leases WHERE origin=? AND released IS NULL AND expires>? AND mode!=\'once\'', (origin, now)).fetchone()[0]
            if n >= MAX_LIVE_PER_ORIGIN:
                c.execute('ROLLBACK')
                return None, 'too many live leases from this address; release what you finished', 429
        dup = [l for l in live if l['agent_h'] == ah and l['mode'] == mode]
        if mode == 'shared' and dup:
            c.execute('ROLLBACK')
            return {'ok': True, 'lease': dup[0]['id'], 'mode': 'shared', 'expires_at': _iso(dup[0]['expires']), 'already_counted': True,
                    'position': [l['id'] for l in live].index(dup[0]['id']) + 1, 'others': len({l['agent_h'] for l in live}) - 1}, None, 200
        lid = 'L' + secrets.token_hex(8)
        tok = secrets.token_urlsafe(24)
        c.execute('INSERT INTO leases (id, key_h, key, agent, agent_h, mode, created, expires, released, token_h, intent, origin, hops) VALUES (?,?,?,?,?,?,?,?,NULL,?,?,?,?)',
                  (lid, kh, key, agent, ah, mode, now, now + ttl, _h(tok, 64), str(intent or '')[:200], str(origin or '')[:64], hops))
        seq, leaf = _append(c, 'claim', {'lease': lid, 'key_h': kh, 'agent_h': ah, 'mode': mode, 'expires': now + ttl, 'hops': hops})
        c.execute('COMMIT')
        out = {'ok': True, 'protocol': VERSION, 'lease': lid, 'token': tok, 'mode': mode, 'key': key, 'expires_at': _iso(now + ttl), 'ttl_seconds': ttl,
               'position': len(live) + 1, 'others': len({l['agent_h'] for l in live} - {ah}), 'hops_left': hops, 'log_seq': seq, 'leaf': leaf,
               'keep': 'the token is shown once; it refreshes and releases this lease',
               'duty': 'refresh before it expires or it is gone; release when finished and mark the outcome; pass hops_left minus one when you delegate'}
        if mode == 'once':
            out['first'] = True
        return out, None, 200
    except Exception:
        try:
            c.execute('ROLLBACK')
        except Exception:
            pass
        raise
    finally:
        c.close()


def mark(key, agent, kind, note='', evidence='', origin='', _c=None):
    """Leave a trace for the next reader. Returns (result, error, status)."""
    key, err = norm_key(key)
    if err:
        return None, err, 400
    agent, err = norm_agent(agent)
    if err:
        return None, err, 400
    kind = str(kind or '').lower()
    if kind not in MARK_KINDS:
        return None, 'kind must be one of: ' + ', '.join(sorted(MARK_KINDS)), 400
    note = re.sub(r'\s+', ' ', str(note or '')).strip()[:280]
    evidence = str(evidence or '').strip()[:300]
    now = int(_now())
    kh, ah = _h(key), _h(agent)
    c = _c or db()
    try:
        if not _c:
            c.execute('BEGIN IMMEDIATE')
        if origin:
            n = c.execute('SELECT COUNT(*) FROM marks WHERE key_h=? AND origin=? AND at>?', (kh, origin, now - 86400)).fetchone()[0]
            if n >= 3:
                if not _c:
                    c.execute('ROLLBACK')
                return None, 'three marks on one key from one address within a day is the limit', 429
        worked = c.execute('SELECT 1 FROM leases WHERE key_h=? AND agent_h=? LIMIT 1', (kh, ah)).fetchone()
        weight = (1.0 if worked else 0.5) * (1.0 if evidence else 0.7)
        seq, leaf = _append(c, 'mark', {'key_h': kh, 'agent_h': ah, 'kind': kind, 'note_h': _h(note) if note else None,
                                        'evidence_h': _h(evidence) if evidence else None, 'weight': round(weight, 2)})
        c.execute('INSERT INTO marks (seq, key_h, key, agent, agent_h, kind, note, evidence, at, origin, weight) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                  (seq, kh, key, agent, ah, kind, note, evidence, now, str(origin or '')[:64], weight))
        if kind != 'note':
            c.execute('DELETE FROM looks WHERE key_h=? AND agent_h=?', (kh, ah))                         # the marker has finished with it
        if not _c:
            c.execute('COMMIT')
        return {'ok': True, 'protocol': VERSION, 'key': key, 'kind': kind, 'weight': round(weight, 2), 'log_seq': seq, 'leaf': leaf,
                'fades': 'this mark halves every %d days' % (HALF_LIFE[kind] // 86400),
                'weight_rule': 'full weight when you held a lease on this key and gave evidence; less otherwise'}, None, 200
    except Exception:
        if not _c:
            try:
                c.execute('ROLLBACK')
            except Exception:
                pass
        raise
    finally:
        if not _c:
            c.close()


def release(lease, token, outcome=None, note='', evidence='', origin=''):
    """Give the crossing back. outcome done or failed also leaves a mark."""
    now = int(_now())
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        l = c.execute('SELECT * FROM leases WHERE id=?', (str(lease or ''),)).fetchone()
        if not l or not token or l['token_h'] != _h(str(token), 64):
            c.execute('ROLLBACK')
            return None, 'lease and token do not match', 403
        if l['mode'] == 'once':
            c.execute('ROLLBACK')
            return None, 'a once key is not released: it exists so that the work is never done twice; mark its outcome instead', 409
        if l['released'] is not None:
            c.execute('ROLLBACK')
            return {'ok': True, 'lease': l['id'], 'already_released': True}, None, 200
        c.execute('UPDATE leases SET released=? WHERE id=?', (now, l['id']))
        c.execute('DELETE FROM looks WHERE key_h=? AND agent_h=?', (l['key_h'], l['agent_h']))       # no longer on this work
        seq, leaf = _append(c, 'release', {'lease': l['id'], 'key_h': l['key_h'], 'held_seconds': now - l['created'], 'in_time': l['expires'] > now})
        m = None
        oc = str(outcome or '').lower()
        if oc in MARK_KINDS:
            m, err, st = mark(l['key'], l['agent'], oc, note, evidence, origin, _c=c)
        c.execute('COMMIT')
        return {'ok': True, 'protocol': VERSION, 'lease': l['id'], 'released_at': _iso(now), 'log_seq': seq, 'mark': m}, None, 200
    except Exception:
        try:
            c.execute('ROLLBACK')
        except Exception:
            pass
        raise
    finally:
        c.close()


def head():
    c = db()
    try:
        r = c.execute('SELECT seq, chain, at FROM log ORDER BY seq DESC LIMIT 1').fetchone()
        a = c.execute('SELECT * FROM anchors ORDER BY seq DESC LIMIT 1').fetchone()
        return {'protocol': VERSION, 'size': r['seq'] if r else 0, 'chain': r['chain'] if r else '', 'at': _iso(r['at']) if r else None,
                'last_anchor': dict(seq=a['seq'], chain=a['chain'], at=_iso(a['at']), astralock_event=a['astralock_event'], leaf_index=a['leaf_index']) if a else None,
                'rule': 'leaf[n] = sha256 of the canonical JSON of {seq, at, kind, body}; chain[n] = sha256 of chain[n-1] followed by leaf[n], both as hex text; chain[0] is empty'}
    finally:
        c.close()


def proof(seq):
    """Everything a third party needs to check that one entry is in the log, up to the next anchored head."""
    try:
        seq = int(seq)
    except (TypeError, ValueError):
        return None, 'seq must be a number'
    c = db()
    try:
        e = c.execute('SELECT * FROM log WHERE seq=?', (seq,)).fetchone()
        if not e:
            return None, 'no such entry'
        prev = c.execute('SELECT chain FROM log WHERE seq=?', (seq - 1,)).fetchone()
        a = c.execute('SELECT * FROM anchors WHERE seq>=? ORDER BY seq LIMIT 1', (seq,)).fetchone()
        upto = a['seq'] if a else c.execute('SELECT MAX(seq) FROM log').fetchone()[0]
        upto = min(upto, seq + 2000)
        later = [r['leaf'] for r in c.execute('SELECT leaf FROM log WHERE seq>? AND seq<=? ORDER BY seq', (seq, upto))]
        return {'protocol': VERSION, 'entry': {'seq': e['seq'], 'at': e['at'], 'kind': e['kind'], 'body': json.loads(e['body'])},
                'leaf': e['leaf'], 'chain_before': prev['chain'] if prev else '', 'chain_at_entry': e['chain'], 'later_leaves': later,
                'reaches_seq': upto,
                'anchor': dict(seq=a['seq'], chain=a['chain'], astralock_event=a['astralock_event'], leaf_index=a['leaf_index'],
                               verify='https://astranl.com/api/astralock/verify/' + str(a['astralock_event'])) if a and a['seq'] == upto else None,
                'check': ['leaf must equal sha256 of the canonical JSON of entry: keys sorted, separators comma and colon, UTF-8',
                          'chain_at_entry must equal sha256 of chain_before followed by leaf',
                          'fold later_leaves the same way; the result must equal the anchor chain',
                          'the anchor chain is the payload of the named AstraLock event, which is signed and sits in a public Merkle log'],
                'not_anchored_yet': None if (a and a['seq'] == upto) else 'the head is anchored every ten minutes; ask again later for the anchor'}, None
    finally:
        c.close()


def stats():
    now = int(_now())
    c = db()
    try:
        q = lambda s, *a: c.execute(s, a).fetchone()[0]
        return {'live_leases': q('SELECT COUNT(*) FROM leases WHERE released IS NULL AND expires>?', now),
                'keys_with_live_leases': q('SELECT COUNT(DISTINCT key_h) FROM leases WHERE released IS NULL AND expires>?', now),
                'agents_ever': q('SELECT COUNT(DISTINCT agent_h) FROM leases'), 'origins_ever': q('SELECT COUNT(DISTINCT origin) FROM leases'),
                'claims_ever': q('SELECT COUNT(*) FROM leases'), 'marks_ever': q('SELECT COUNT(*) FROM marks'), 'log_size': q('SELECT COALESCE(MAX(seq),0) FROM log'),
                'at': _iso(now)}
    finally:
        c.close()


def protocol():
    return {'protocol': VERSION, 'name': 'ACX-1, the AstraNL Crossing', 'operator': 'AstraNL, Zaandam, Netherlands, KvK 88449335',
            'purpose': 'A shared crossing for agents that do not know each other. Before work: look. If the light allows: claim. '
                       'Before spending: check. After work: mark. No account, no key, no wallet. Free. Signed proof is the paid part.',
            'moves': [
                {'move': 'look', 'when': 'before starting any work or using any contested resource', 'gives': 'GREEN, AMBER or RED with the reasons, who else is on it, the trail earlier agents left, whether it is worth your effort'},
                {'move': 'claim', 'when': 'the light allows and you start', 'gives': 'a lease that dies unless refreshed: shared to be counted, exclusive to be alone, once so that the work is never done twice by anybody'},
                {'move': 'check', 'when': 'before any spend of money or significant effort', 'gives': 'GO, CAUTION or STOP from the ABA-1 fuse'},
                {'move': 'mark', 'when': 'you finished, failed, were paid or were not paid', 'gives': 'a trace for the next agent, fading with time, sealed in the log'}],
            'key': 'any URL or stable name of the work or resource: a task link, an issue link, an endpoint, a file path with its repository. Everyone who means the same thing must write the same key.',
            'agent': 'any stable name or address you choose. No registration.',
            'rules': {'lease_seconds': [TTL_MIN, TTL_DEFAULT, TTL_MAX], 'exclusive_max_hours': EXCLUSIVE_MAX_AGE // 3600, 'clearance_seconds': CLEARANCE,
                      'once_days': ONCE_TTL // 86400, 'hops_max': MAX_HOPS, 'backoff_seconds': [BACKOFF_BASE, BACKOFF_CAP],
                      'mark_kinds': sorted(MARK_KINDS), 'mark_half_life_days': {k: v // 86400 for k, v in HALF_LIFE.items()}, 'trail_ceiling': TRAIL_CEILING,
                      'live_leases_per_address': MAX_LIVE_PER_ORIGIN},
            'light': {'RED': 'another agent holds it exclusively, it was taken once, the venue closed it or shows no funding, the trail is bad, or it is not worth it on your numbers',
                      'AMBER': 'clearance after a lease ran out, others already on it for the places there are, or recent failures',
                      'GREEN': 'free of known holders and known trouble; not a promise that it is safe or worth doing'},
            'learned_from': {'traffic lights': 'the light itself; clearance interval after a lease runs out; no release into a blocked crossing; metering at the edge',
                             'ant colonies': 'marks on the shared place instead of messages; evaporation; a ceiling on every trail; staying out when it is crowded',
                             'brain': 'exclusive work inhibited by default and released to one; a budget of live leases; report deviations, not everything',
                             'internet': 'soft state that dies unless refreshed; hop count on delegation; jittered exponential backoff; one narrow format; refuse malformed input loudly',
                             'proof': 'append-only hash chain anchored in a signed public Merkle log; stated invariants tested over random interleavings'},
            'invariants': ['at most one live exclusive or once lease per key', 'a lease not refreshed is dead after its expiry', 'the log only grows and each entry binds all earlier ones',
                           'look is never GREEN for you while another agent holds the key exclusively', 'a once key is granted to exactly one caller'],
            'limits': ['leases are advice between cooperating agents, not locks on the resource itself', 'marks are statements by agents; weight is higher with a lease and evidence, and they are not verified facts',
                       'the count of others is what this crossing and the venue can see, not everyone in the world'],
            'licence': 'The protocol may be implemented by anyone, free of charge.'}
