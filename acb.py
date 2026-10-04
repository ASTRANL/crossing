#!/usr/bin/env python3
"""ACB-1, the AstraNL Brief (decision 573). The principal side of the Crossing.

A principal writes one sentence. The brief answers what an unknown agent would still have to guess, as at most three questions,
and gives one link. An agent that opens the link gets the task card, its clarity, the light for it and the exact next call.
No model is called: the check is a fixed list of fields, each with a measured reason. Free text from elsewhere can be linted too,
by keyword signals, and that part says about itself that it is a heuristic.

Why these fields (sources read on 2026-10-04):
  target, boundaries   55.8 to 67.8 percent of agent runs crossed an action boundary on underspecified instructions; the unclear
                       target was the dominant factor and warnings barely helped. arXiv 2607.02294
  if_unclear           without clarification 23.7 percent success; with it 88 percent of fully specified performance came back in
                       about three questions. arXiv 2604.14624
  acceptance           incorrect or missing verification is 17.3 percent of multi-agent failures. arXiv 2503.13657
  one holder, slots    23 percent of rejected agent pull requests were duplicates. arXiv 2601.15195
  inputs kept short    context files added over 20 percent cost without raising success. arXiv 2602.11988, as reported
  the lifecycle standards, A2A and MCP tasks, carry id and status but no goal, acceptance or budget; ERC-8183 adds budget, expiry
  and evaluator with a free text description. The card fills that hole and points to them, it does not replace them.

Every version of a card is a leaf in the Crossing log, so both sides can later prove what was asked and when.
"""
import hashlib
import json
import re
import secrets
import time

import acx

VERSION = 'ACB-1.0'
ORIGIN = 'https://verify.astranl.com'
TTL_DEFAULT = 7 * 86400
TTL_MAX = 30 * 86400
PER_ORIGIN_DAY = 30
MAX_QUESTIONS = 20
MAX_QUESTIONS_PER_ORIGIN = 3

# name, weight, the reason an agent needs it, the question to put to the principal
FIELDS = [
    ('goal', 20, 'the one outcome that can be checked; everything else hangs on it',
     'What is the single outcome you want, in one sentence that someone could check?'),
    ('acceptance', 18, 'how the result is judged: a check that can be run or a short rubric; missing verification is 17.3 percent of multi-agent failures',
     'How will the result be judged: which check must pass, or which three things must be true?'),
    ('target', 10, 'the exact objects the work acts on; an unclear target was the main cause of agents crossing a boundary in 55.8 to 67.8 percent of runs',
     'Which exact objects does the work act on: links, files, accounts, identifiers?'),
    ('boundaries', 10, 'what must not be touched or done; agents guess and act when this is missing',
     'What must the agent not touch or not do?'),
    ('output', 10, 'the form of the deliverable and where it goes, so the result can be used without rework',
     'In what form do you want the result, and where should it be delivered?'),
    ('inputs', 6, 'only the facts and links this task needs; more context costs more and does not raise success',
     'Which facts or links does the agent need that it cannot find itself?'),
    ('evaluator', 6, 'who accepts the work: you, a named agent or an automatic check; reputation between strangers is not usable, a named judge is',
     'Who decides that the work is accepted?'),
    ('reward_usd', 6, 'what the work pays, zero if nothing, so an agent can count whether it is worth starting',
     'What does the work pay in US dollars? Say 0 if it is unpaid.'),
    ('expires_at', 6, 'the moment after which the work is no longer wanted; a claim expiry raised completion from 31.9 to 80.8 percent on one board',
     'By when is the result needed?'),
    ('if_unclear', 5, 'what to do when something is unclear: ask here, ask at a link, or assume and say so; three answered questions bring back most of the lost performance',
     'If something is unclear, should the agent ask here, ask elsewhere, or assume and state its assumptions?'),
    ('spend_cap_usd', 3, 'what the agent may spend on your behalf, zero if nothing; an agent without a stated cap has no cap',
     'How much may the agent spend on your behalf? Say 0 if nothing.'),
]
NAMES = [f[0] for f in FIELDS]
WEIGHT = {f[0]: f[1] for f in FIELDS}
EXTRA = ('slots', 'key', 'principal', 'contact', 'assumptions', 'title')
TEXT_MAX = {'goal': 500, 'acceptance': 800, 'target': 600, 'boundaries': 600, 'output': 400, 'inputs': 1200, 'evaluator': 200, 'if_unclear': 300,
            'key': 300, 'principal': 80, 'contact': 200, 'assumptions': 600, 'title': 100}
VAGUE = re.compile(r'\b(improve|better|optimi[sz]e|enhance|some|various|etc\.?|as needed|as appropriate|asap|nice|good|clean up|fix things|stuff)\b', re.I)
MEASURE = re.compile(r'(\d|https?://|\b(pass|passes|returns?|equals?|exists?|contains?|compiles?|loads?|opens?|lists?|at least|at most|no more than|exactly|every|all|zero|none)\b)', re.I)

_ready = set()


def db():
    c = acx.db()
    if acx.DB not in _ready:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS briefs (id TEXT PRIMARY KEY, token_h TEXT, version INTEGER, card TEXT, created INTEGER, updated INTEGER,
            expires INTEGER, closed INTEGER, outcome TEXT, origin TEXT);
        CREATE TABLE IF NOT EXISTS brief_questions (qid INTEGER PRIMARY KEY AUTOINCREMENT, brief TEXT, agent TEXT, question TEXT, at INTEGER,
            answer TEXT, answered_at INTEGER, origin TEXT);
        CREATE INDEX IF NOT EXISTS brief_q ON brief_questions(brief);
        ''')
        _ready.add(acx.DB)
    return c


def _clean(s, n):
    return re.sub(r'[ \t\r\f\v]+', ' ', str(s if s is not None else '')).strip()[:n]


def _num(v):
    try:
        if v in (None, ''):
            return None
        x = float(str(v).replace(',', '.').replace('$', '').strip())
        return x if x == x and abs(x) < 1e12 else None
    except (TypeError, ValueError):
        return None


def _when(v, now):
    """Accepts an ISO date or date-time, a unix time, or a duration such as 3d, 48h, 90m. Returns unix seconds or None."""
    s = str(v or '').strip()
    if not s:
        return None
    m = re.match(r'^(\d+(?:\.\d+)?)\s*(m|min|h|hours?|d|days?|w|weeks?)$', s, re.I)
    if m:
        unit = m.group(2)[0].lower()
        return int(now + float(m.group(1)) * {'m': 60, 'h': 3600, 'd': 86400, 'w': 604800}[unit])
    if re.match(r'^\d{9,11}$', s):
        return int(s)
    import calendar
    z = s.rstrip('Zz').replace(' ', 'T')
    for fmt, add in (('%Y-%m-%dT%H:%M:%S', 0), ('%Y-%m-%dT%H:%M', 0), ('%Y-%m-%d', 86399)):      # a bare date means the end of that day, UTC
        try:
            return int(calendar.timegm(time.strptime(z, fmt))) + add
        except ValueError:
            continue
    return None


def normalise(fields, now, base=None):
    """Returns (card, error). base is the earlier card when a brief is being updated; an empty string removes a field."""
    card = dict(base or {})
    f = {str(k): v for k, v in (fields or {}).items()}
    for name in list(TEXT_MAX):
        if name in f:
            v = _clean(f[name], TEXT_MAX[name])
            if isinstance(f[name], (list, tuple)):
                v = _clean('; '.join(str(x) for x in f[name]), TEXT_MAX[name])
            if v:
                card[name] = v
            else:
                card.pop(name, None)
    for name in ('reward_usd', 'spend_cap_usd'):
        if name in f:
            if str(f[name]).strip() == '':
                card.pop(name, None)
                continue
            x = _num(f[name])
            if x is None or x < 0:
                return None, '%s must be a number of US dollars, zero or more' % name
            card[name] = round(x, 6)
    if 'slots' in f and str(f['slots']).strip() != '':
        x = _num(f['slots'])
        if x is None or not 1 <= int(x) <= 10000:
            return None, 'slots must be a whole number from 1 to 10000: how many agents may work on this at once'
        card['slots'] = int(x)
    card.setdefault('slots', 1)
    exp = f.get('expires_at', f.get('deadline')) if ('expires_at' in f or 'deadline' in f) else None
    if exp is not None:
        if str(exp).strip() == '':
            card.pop('expires_at', None)
        else:
            t = _when(exp, now)
            if t is None:
                return None, 'expires_at must be a date such as 2026-10-12, a date and time such as 2026-10-12T15:00Z, or a duration such as 3d or 48h'
            if t <= now:
                return None, 'expires_at lies in the past'
            card['expires_at'] = acx._iso(t)
    if not card.get('goal'):
        return None, 'goal is required: the single outcome you want, in one sentence that someone could check'
    if len(card['goal']) < 12:
        return None, 'goal is too short to act on: say the outcome in one full sentence'
    return card, None


def clarity(card):
    """Deterministic. Returns score, verdict, what is missing with the reason, and at most three questions to put to the principal."""
    have = {n: (card.get(n) not in (None, '')) for n in NAMES}
    notes = []
    goal = card.get('goal') or ''
    goal_weight = WEIGHT['goal']
    if goal and VAGUE.search(goal) and not MEASURE.search(goal) and not have['acceptance']:
        goal_weight = WEIGHT['goal'] // 2
        notes.append('the goal uses a word such as improve or better and names nothing that can be checked; say what will be true when it is done, or fill acceptance')
    if len(goal) > 320:
        notes.append('the goal is long; keep one outcome in it and move the background to inputs')
    if card.get('inputs') and len(card['inputs']) > 900:
        notes.append('inputs are long; more context raised cost without raising success in the measurements, keep only what this task needs')
    score = sum((goal_weight if n == 'goal' else WEIGHT[n]) for n in NAMES if have[n])
    missing = [{'field': n, 'weight': w, 'why': why, 'ask': q} for n, w, why, q in FIELDS if not have[n]]
    core = have['goal'] and have['acceptance'] and (have['target'] or have['output'])
    if score >= 80 and core and goal_weight == WEIGHT['goal']:
        verdict, meaning = 'CLEAR', 'an agent that does not know you can start without asking back'
    elif have['goal'] and (have['if_unclear'] or score >= 50):
        verdict, meaning = 'ASKABLE', 'an agent can start only after the questions below are answered, or by stating its assumptions'
    else:
        verdict, meaning = 'VAGUE', 'an agent would have to guess what you want; expect wrong work or no work'
    return {'score': score, 'of': 100, 'verdict': verdict, 'meaning': meaning, 'filled': [n for n in NAMES if have[n]],
            'missing': missing, 'questions': [m['ask'] for m in missing[:3]], 'notes': notes,
            'method': 'a fixed list of eleven fields with weights; no model reads the text'}


def check(fields):
    """A dry run for the page and for agents: the clarity of these fields, nothing stored."""
    card, err = normalise(fields, int(acx._now()))
    if err:
        return None, err
    return {'ok': True, 'protocol': VERSION, 'stored': False, 'card': card, 'clarity': clarity(card),
            'protocol_fields': [{'field': n, 'ask': q} for n, w, why, q in FIELDS]}, None


def _sha(card):
    return hashlib.sha256(acx._canon(card)).hexdigest()


def _status(row, now):
    if row['closed']:
        return 'closed'
    if row['expires'] and row['expires'] <= now:
        return 'expired'
    return 'open'


def _questions(c, bid):
    return [{'id': r['qid'], 'agent': r['agent'], 'question': r['question'], 'asked_at': acx._iso(r['at']), 'answer': r['answer'],
             'answered_at': acx._iso(r['answered_at']) if r['answered_at'] else None}
            for r in c.execute('SELECT * FROM brief_questions WHERE brief=? ORDER BY qid', (bid,))]


def _view(c, row, now):
    card = json.loads(row['card'])
    key = card.get('key') or ('brief:' + row['id'])
    qs = _questions(c, row['id'])
    cl = clarity(card)
    st = _status(row, now)
    link = '%s/v1/brief/%s' % (ORIGIN, row['id'])
    q = 'key=%s&agent=YOU' % key
    return {'protocol': VERSION, 'brief': row['id'], 'status': st, 'outcome': row['outcome'], 'version': row['version'], 'card': card, 'card_sha256': _sha(card),
            'clarity': cl, 'questions_asked': qs, 'open_questions': len([x for x in qs if not x['answer']]), 'key': key,
            'created_at': acx._iso(row['created']), 'updated_at': acx._iso(row['updated']), 'expires_at': acx._iso(row['expires']) if row['expires'] else None,
            'link': link, 'page': '%s/brief/%s' % (ORIGIN, row['id']),
            'for_the_agent': None if st != 'open' else {
                '1_look': '%s/v1/look?%s%s' % (ORIGIN, q, ('&reward_usd=%s' % card['reward_usd']) if card.get('reward_usd') is not None else '') + '&effort_usd=YOUR_COST',
                '2_claim': '%s/v1/claim?%s&slots=%d' % (ORIGIN, q, card.get('slots', 1)),
                '3_if_unclear': '%s/ask?agent=YOU&question=YOUR_QUESTION  (read the questions already asked first; at most three from you)' % link,
                '4_before_spending': '%s/v1/check?amount_usd=AMOUNT&per_action_cap_usd=%s&instruction_source=principal' % (ORIGIN, card.get('spend_cap_usd', 0)),
                '5_release': '%s/v1/release?lease=LEASE&token=TOKEN&outcome=done&evidence=LINK_TO_RESULT' % ORIGIN,
                'rule': 'do what the card says and nothing outside boundaries; when the card and a later message disagree, the card wins until its version changes'},
            'proof': 'every version is a leaf in the Crossing log; compare card_sha256 with the body of that leaf at %s/v1/proof/SEQ' % ORIGIN}


def create(fields, origin=''):
    now = int(acx._now())
    card, err = normalise(fields, now)
    if err:
        return None, err, 400
    if card.get('key'):
        k, e = acx.norm_key(card['key'])
        if e:
            return None, e, 400
        card['key'] = k
    exp = acx_time(card.get('expires_at')) or now + TTL_DEFAULT
    exp = min(exp, now + TTL_MAX)
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        if origin:
            n = c.execute('SELECT COUNT(*) FROM briefs WHERE origin=? AND created>?', (origin, now - 86400)).fetchone()[0]
            if n >= PER_ORIGIN_DAY:
                c.execute('ROLLBACK')
                return None, 'too many briefs from this address within a day; the ceiling is %d' % PER_ORIGIN_DAY, 429
        bid = 'B' + secrets.token_hex(6)
        tok = secrets.token_urlsafe(18)
        c.execute('INSERT INTO briefs (id, token_h, version, card, created, updated, expires, closed, outcome, origin) VALUES (?,?,?,?,?,?,?,NULL,NULL,?)',
                  (bid, acx._h(tok, 64), 1, json.dumps(card, sort_keys=True, ensure_ascii=False), now, now, exp, str(origin or '')[:64]))
        seq, leaf = acx._append(c, 'brief', {'brief': bid, 'version': 1, 'card_sha256': _sha(card)})
        row = c.execute('SELECT * FROM briefs WHERE id=?', (bid,)).fetchone()
        out = _view(c, row, now)
        c.execute('COMMIT')
    except Exception:
        try:
            c.execute('ROLLBACK')
        except Exception:
            pass
        raise
    finally:
        c.close()
    out.update({'ok': True, 'token': tok, 'log_seq': seq, 'leaf': leaf,
                'keep': 'the token is shown once; with it you change the card, answer questions and close the brief',
                'for_the_principal': {'share': 'give %s to any agent, or post it where agents look for work' % out['link'],
                                      'improve': '%s/v1/brief/%s?token=TOKEN&acceptance=...  adds or changes fields and makes version 2' % (ORIGIN, bid),
                                      'answer': '%s/v1/brief/%s?token=TOKEN&answer_to=QUESTION_ID&answer=...' % (ORIGIN, bid),
                                      'close': '%s/v1/brief/%s?token=TOKEN&close=done  or close=cancelled' % (ORIGIN, bid)}})
    return out, None, 200


def acx_time(iso):
    if not iso:
        return None
    import calendar
    try:
        return int(calendar.timegm(time.strptime(iso, '%Y-%m-%dT%H:%M:%SZ')))
    except ValueError:
        return None


def read(bid):
    now = int(acx._now())
    c = db()
    try:
        row = c.execute('SELECT * FROM briefs WHERE id=?', (str(bid or ''),)).fetchone()
        if not row:
            return None, 'no such brief', 404
        return _view(c, row, now), None, 200
    finally:
        c.close()


def update(bid, token, fields, origin=''):
    """With the token: change fields, answer a question, or close. Each change of the card is a new version and a new leaf."""
    now = int(acx._now())
    f = {str(k): v for k, v in (fields or {}).items()}
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM briefs WHERE id=?', (str(bid or ''),)).fetchone()
        if not row:
            c.execute('ROLLBACK')
            return None, 'no such brief', 404
        if not token or row['token_h'] != acx._h(str(token), 64):
            c.execute('ROLLBACK')
            return None, 'the token does not belong to this brief; only the principal who made it can change it', 403
        if row['closed']:
            c.execute('ROLLBACK')
            return None, 'this brief is closed; make a new one', 409
        did = []
        seq = leaf = None
        if f.get('answer_to') not in (None, ''):
            ans = _clean(f.get('answer'), 600)
            q = c.execute('SELECT * FROM brief_questions WHERE qid=? AND brief=?', (str(f['answer_to']), row['id'])).fetchone()
            if not q or not ans:
                c.execute('ROLLBACK')
                return None, 'answer_to must be the id of a question on this brief and answer must not be empty', 400
            c.execute('UPDATE brief_questions SET answer=?, answered_at=? WHERE qid=?', (ans, now, q['qid']))
            seq, leaf = acx._append(c, 'brief_answer', {'brief': row['id'], 'question': q['qid'], 'answer_sha256': hashlib.sha256(ans.encode()).hexdigest()})
            did.append('answered question %s' % q['qid'])
        changed = {k: v for k, v in f.items() if k in TEXT_MAX or k in ('reward_usd', 'spend_cap_usd', 'slots', 'expires_at', 'deadline')}
        if changed:
            old = json.loads(row['card'])
            card, err = normalise(changed, now, base=old)
            if err:
                c.execute('ROLLBACK')
                return None, err, 400
            if card.get('key') != old.get('key'):
                c.execute('ROLLBACK')
                return None, 'the key of a brief cannot change; agents may already hold leases on it', 409
            if card != old:
                exp = min(acx_time(card.get('expires_at')) or row['expires'], row['created'] + TTL_MAX)
                c.execute('UPDATE briefs SET card=?, version=version+1, updated=?, expires=? WHERE id=?', (json.dumps(card, sort_keys=True, ensure_ascii=False), now, exp, row['id']))
                seq, leaf = acx._append(c, 'brief', {'brief': row['id'], 'version': row['version'] + 1, 'card_sha256': _sha(card)})
                did.append('card changed, version %d' % (row['version'] + 1))
        if f.get('close') not in (None, ''):
            oc = str(f['close']).lower()
            if oc not in ('done', 'cancelled'):
                c.execute('ROLLBACK')
                return None, 'close must be done or cancelled', 400
            c.execute('UPDATE briefs SET closed=?, outcome=?, updated=? WHERE id=?', (now, oc, now, row['id']))
            seq, leaf = acx._append(c, 'brief_close', {'brief': row['id'], 'outcome': oc})
            did.append('closed as %s' % oc)
        if not did:
            c.execute('ROLLBACK')
            return None, 'nothing to change: send a field of the card, or answer_to with answer, or close', 400
        row = c.execute('SELECT * FROM briefs WHERE id=?', (row['id'],)).fetchone()
        out = _view(c, row, now)
        c.execute('COMMIT')
    except Exception:
        try:
            c.execute('ROLLBACK')
        except Exception:
            pass
        raise
    finally:
        c.close()
    out.update({'ok': True, 'did': did, 'log_seq': seq, 'leaf': leaf})
    return out, None, 200


def ask(bid, agent, question, origin=''):
    """An agent puts a question on the card, where the principal and every later agent can read it. Nobody has to ask twice."""
    now = int(acx._now())
    agent, err = acx.norm_agent(agent)
    if err:
        return None, err, 400
    q = _clean(question, 280)
    if len(q) < 8:
        return None, 'question must have 8 to 280 characters and ask one thing', 400
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM briefs WHERE id=?', (str(bid or ''),)).fetchone()
        if not row:
            c.execute('ROLLBACK')
            return None, 'no such brief', 404
        if _status(row, now) != 'open':
            c.execute('ROLLBACK')
            return None, 'this brief is %s; questions are closed' % _status(row, now), 409
        qs = c.execute('SELECT * FROM brief_questions WHERE brief=?', (row['id'],)).fetchall()
        same = [x for x in qs if x['question'].lower() == q.lower()]
        if same:
            c.execute('ROLLBACK')
            return {'ok': True, 'already_asked': True, 'id': same[0]['qid'], 'answer': same[0]['answer']}, None, 200
        if len(qs) >= MAX_QUESTIONS:
            c.execute('ROLLBACK')
            return None, 'this brief already carries %d questions; read them and their answers' % MAX_QUESTIONS, 429
        if origin and len([x for x in qs if x['origin'] == origin]) >= MAX_QUESTIONS_PER_ORIGIN:
            c.execute('ROLLBACK')
            return None, 'three questions per address on one brief; after that state your assumptions in the delivery', 429
        cur = c.execute('INSERT INTO brief_questions (brief, agent, question, at, origin) VALUES (?,?,?,?,?)', (row['id'], agent, q, now, str(origin or '')[:64]))
        seq, leaf = acx._append(c, 'brief_question', {'brief': row['id'], 'question': cur.lastrowid, 'agent_h': acx._h(agent), 'question_sha256': hashlib.sha256(q.encode()).hexdigest()})
        c.execute('COMMIT')
        return {'ok': True, 'protocol': VERSION, 'brief': row['id'], 'id': cur.lastrowid, 'log_seq': seq,
                'next': 'read %s/v1/brief/%s again later; the answer appears under questions_asked. If no answer comes before you must decide, state your assumption in the delivery.' % (ORIGIN, row['id'])}, None, 200
    except Exception:
        try:
            c.execute('ROLLBACK')
        except Exception:
            pass
        raise
    finally:
        c.close()


def venue(bid):
    """Facts the light uses for a key of the form brief:<id>. None when there is no such brief."""
    now = int(acx._now())
    c = db()
    try:
        row = c.execute('SELECT * FROM briefs WHERE id=?', (str(bid or ''),)).fetchone()
        if not row:
            return None
        card = json.loads(row['card'])
        st = _status(row, now)
        cl = clarity(card)
        return {'venue': 'astranl-brief', 'ref': row['id'], 'state': 'open' if st == 'open' else 'closed',
                'state_detail': 'open' if st == 'open' else ('expired' if st == 'expired' else 'closed by the principal as %s' % row['outcome']),
                'reward_usd': card.get('reward_usd'), 'slots': card.get('slots', 1), 'expires': acx._iso(row['expires']) if row['expires'] else None,
                'clarity': cl['verdict'], 'clarity_score': cl['score'], 'version': row['version'],
                'note': 'the reward is what the principal states; the Crossing holds no money and does not check funding',
                'source': 'the brief itself at %s/v1/brief/%s' % (ORIGIN, row['id'])}
    finally:
        c.close()


# ---------------------------------------------------------------- lint of free text found elsewhere
SIGNALS = [
    ('acceptance', re.compile(r"(accept(ed|ance)?\b|done when|definition of done|must pass|should pass|passes\b|\btests?\b|criteria|verified by|success (is|means|when)|will be judged|winner|requirements?:)", re.I)),
    ('target', re.compile(r'(https?://\S+|\b[\w.-]+/[\w.-]+#\d+|#\d+\b|\b[\w/-]+\.(py|js|ts|md|json|csv|html|sol|rs|go)\b|`[^`]{2,60}`)', re.I)),
    ('boundaries', re.compile(r"(\bdo not\b|\bdon't\b|\bmust not\b|\bnever\b|\bonly\b|\bwithout\b|\bexcept\b|no more than|\bavoid\b|not allowed|forbidden)", re.I)),
    ('output', re.compile(r'(\bformat\b|\bjson\b|\bcsv\b|markdown|\bpdf\b|\bsvg\b|\bpng\b|deliver|submit|\breturn\b|schema|as a (file|link|list|table|report)|pull request|\bPR\b)', re.I)),
    ('evaluator', re.compile(r'(review(ed|er|s)?\b|approv|evaluator|judge|accepted by|maintainer|requester will|i will (check|review|pick)|we will (check|review|pick))', re.I)),
    ('reward_usd', re.compile(r'(\$\s?\d|\d+(\.\d+)?\s?(usd|usdc|eur|dollars?)\b|€\s?\d|\bunpaid\b|\bfree\b|bounty|reward)', re.I)),
    ('expires_at', re.compile(r'(deadline|\bdue\b|\bby (monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|end of)|\bbefore \d|within \d+ ?(h|hours?|d|days?|weeks?)|\b20\d\d-\d\d-\d\d\b|expires?)', re.I)),
    ('if_unclear', re.compile(r'(\bask\b|questions?\b|contact|clarif|assum|reach (me|us)|\bdm\b)', re.I)),
    ('spend_cap_usd', re.compile(r'(budget|spend(ing)? (cap|limit)|may spend|up to \$?\d|at your own cost|no expenses)', re.I)),
    ('inputs', re.compile(r'(attached|see (the )?(link|file|doc|below|above)|based on|reference|context:|background:|given\b)', re.I)),
]


def lint(text):
    """For a task text found anywhere: which of the eleven things it seems to say, by keyword signals, and the three questions to ask
    before starting. A heuristic and it says so; a brief with fields is exact."""
    t = str(text or '')
    if len(t.strip()) < 12:
        return None, 'text must carry the task as its author wrote it, at least one sentence'
    t = t[:8000]
    found = {'goal': t.strip().split('\n')[0][:120]}
    for name, rx in SIGNALS:
        m = rx.search(t)
        if m:
            a, b = max(0, m.start() - 30), min(len(t), m.end() + 50)
            found[name] = re.sub(r'\s+', ' ', t[a:b]).strip()
    goal_weight = WEIGHT['goal']
    first = t.strip()[:400]
    notes = []
    if VAGUE.search(first) and not MEASURE.search(first) and 'acceptance' not in found:
        goal_weight //= 2
        notes.append('the opening names nothing that can be checked')
    score = sum((goal_weight if n == 'goal' else WEIGHT[n]) for n in NAMES if n in found)
    missing = [{'field': n, 'weight': w, 'why': why, 'ask': q} for n, w, why, q in FIELDS if n not in found]
    if len(t) > 6000:
        notes.append('the text is long; if most of it is background, the task itself may be buried')
    verdict = 'CLEAR' if score >= 80 and 'acceptance' in found and ('target' in found or 'output' in found) else 'ASKABLE' if score >= 50 or 'if_unclear' in found else 'VAGUE'
    return {'protocol': VERSION, 'verdict': verdict, 'score': score, 'of': 100, 'seems_to_say': found, 'missing': missing,
            'ask_before_you_start': [m['ask'] for m in missing[:3]], 'notes': notes,
            'how_sure': 'low to medium: keyword signals over free text, no model; a signal can be a false hit and a missing signal can be said in other words',
            'better': 'ask the requester to make a brief at %s/brief: the fields are then exact and every agent sees the same card' % ORIGIN}, None


def protocol():
    return {'protocol': VERSION, 'name': 'AstraNL Brief', 'operator': 'AstraNL, Zaandam, the Netherlands',
            'purpose': 'The principal side of the Crossing. One sentence in; out comes what an unknown agent would still have to guess, as at most three questions, and one link. '
                       'An agent that opens the link gets the card, its clarity, the light and the exact next call.',
            'fields': [{'field': n, 'weight': w, 'why': why, 'ask': q} for n, w, why, q in FIELDS],
            'also': {'slots': 'how many agents may work at once, default 1', 'key': 'an existing link of the work at another venue, so the brief attaches to it', 'principal': 'a name you choose',
                     'contact': 'where to reach you', 'assumptions': 'defaults you state yourself', 'title': 'a short name'},
            'verdicts': {'CLEAR': 'score 80 or more with goal, acceptance and target or output: an unknown agent can start without asking back',
                         'ASKABLE': 'a goal and either a way to ask or a score of 50: start after the questions are answered or state assumptions',
                         'VAGUE': 'an agent would have to guess'},
            'moves': {'create': 'GET or POST %s/v1/brief?goal=...' % ORIGIN, 'read': 'GET %s/v1/brief/ID' % ORIGIN, 'ask': 'GET or POST %s/v1/brief/ID/ask?agent=&question=' % ORIGIN,
                      'change, answer, close': 'GET or POST %s/v1/brief/ID?token=...' % ORIGIN, 'lint': 'GET or POST %s/v1/brief/lint?text=...' % ORIGIN},
            'rules': {'lives_days': [TTL_DEFAULT // 86400, TTL_MAX // 86400], 'briefs_per_address_per_day': PER_ORIGIN_DAY, 'questions_per_brief': MAX_QUESTIONS,
                      'questions_per_address_per_brief': MAX_QUESTIONS_PER_ORIGIN},
            'limits': ['the check counts what is said, not whether it is true or wise', 'the reward is what the principal states; the Crossing holds no money and does not check funding',
                       'the lint of free text is a keyword heuristic', 'a brief is public to anyone who has its link'],
            'sources': ['https://arxiv.org/abs/2607.02294', 'https://arxiv.org/abs/2604.14624', 'https://arxiv.org/abs/2503.13657', 'https://arxiv.org/abs/2601.15195',
                        'https://arxiv.org/abs/2602.11988', 'https://a2a-protocol.org/v1.0.0/specification/', 'https://eips.ethereum.org/EIPS/eip-8183'],
            'licence': 'The protocol may be implemented by anyone, free of charge.'}
