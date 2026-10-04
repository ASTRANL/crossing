#!/usr/bin/env python3
"""ACA-1, the AstraNL Agent Coordination Audit (decision 561, founder order 2026-10-04).

The sister of ABA-1. ABA-1 asks how an agent can lose its budget; ACA-1 asks how a system of agents loses work:
duplicated effort, repeated side effects, loops, amplified errors, lost context, locks nobody releases. Sixteen
patterns, each with a measurement from the research record (RESEARCH.md) and with the move that closes it.

Deterministic, standard library only. Answers are self-declared; UNKNOWN counts as open; a control counts only
when the runtime enforces it, not when the prompt asks for it.
"""
VERSION = 'ACA-1.0'
ANSWERS = ('yes', 'partial', 'no', 'unknown')
POINTS = {'yes': 1.0, 'partial': 0.5, 'no': 0.0, 'unknown': 0.0}
SCOPES = ('parallel', 'tools', 'handoff', 'market')

# key, title, weight, scopes, question, what goes wrong, measured, source, fix, crossing move
C = [
    ('claim_before_work', 'No claim on shared work', 9, ('parallel', 'market'),
     'Before an agent starts a piece of work that another agent could also pick, does it take a claim that the others can see?',
     'Agents pick the same work, redo it and overwrite each other.',
     'Two cooperating coding agents succeeded about 25 percent against about 50 percent for one agent; work overlap in 33.2 percent of failures. One market drew 44 submissions per task.',
     'https://arxiv.org/html/2601.13295v1',
     'Take a visible claim on a declared scope before any work; refuse to start when another holds it.', 'claim'),
    ('leases_expire', 'Locks that nobody releases', 7, ('parallel',),
     'Do claims and locks expire by themselves unless the holder refreshes them?',
     'A holder that crashes or forgets keeps the lock; the others wait or stall.',
     'Twenty agents sharing a lock file slowed to the throughput of two or three because holders kept locks too long or forgot to release them.',
     'https://cursor.com/blog/scaling-agents',
     'Make every lock a lease with a short life that must be refreshed, and cap how long one holder may keep it.', 'claim'),
    ('idempotent_side_effects', 'Side effects repeat on retry', 9, ('tools', 'market'),
     'Does every action with an outside effect, a payment, an order, a message, a write, carry a key that makes a repeat harmless?',
     'A retry after a timeout, a redelivery or a restart does the thing twice.',
     'Frontier models repeated a side effect in 74 percent of redelivered requests and 56 percent of late commits; a key on every side effect cut that to 7 percent.',
     'https://arxiv.org/html/2609.29095v1',
     'Derive a key from the intent and check it before acting; keep the key outside the agent\'s own memory.', 'claim with mode once'),
    ('stop_condition', 'No stop condition', 8, SCOPES,
     'Is there an explicit end state for every task, checked by the runtime, with a ceiling on steps and on repeated identical calls?',
     'Agents repeat steps, do not notice they are finished, or stop early.',
     'Step repetition is 15.7 percent of failures in 1,642 multi-agent traces, unawareness of termination conditions 12.4 percent.',
     'https://arxiv.org/abs/2503.13657',
     'Write the end state down before the work starts; enforce a step ceiling and a breaker on identical calls in the runner.', 'check'),
    ('independent_verification', 'No independent verification point', 9, SCOPES,
     'Is the result of an agent checked by something other than that agent before it is used or passed on?',
     'Errors pass from agent to agent and grow.',
     'Independent agents amplified errors 17.2 times against 4.4 times with one validation point; one added verification step gave plus 15.6 points of task success.',
     'https://arxiv.org/html/2512.08296',
     'Put one acceptance check with evidence between producing a result and using it.', 'mark with evidence'),
    ('structured_handoff', 'Context lost at handoff', 7, ('handoff',),
     'When work passes between agents, does it pass as a fixed structure with the artifacts by reference, not as a retelling?',
     'The receiver guesses what the sender meant; a supervisor that paraphrases loses information.',
     'Inter-agent misalignment is 32.3 percent of multi-agent failures; forwarding replies directly instead of paraphrasing gave nearly 50 percent better results in a vendor benchmark.',
     'https://www.langchain.com/blog/benchmarking-multi-agent-architectures',
     'Hand over a fixed record: goal, end state, what was done, artifacts by link, what is open. No free retelling.', 'mark'),
    ('hop_limit', 'Delegation without a hop limit', 6, ('handoff',),
     'Does every delegated task carry a remaining hop count or budget that is reduced at each handoff and stops the chain at zero?',
     'Work circles between agents until someone reads the invoice.',
     'One reported loop between two agents ran eleven days; the report is first-person and its figures are inconsistent. The mechanism, a follow-the-predecessor rule with no outside check, is the ant mill.',
     'https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33',
     'Pass a hop count with every delegation; at zero return the work to its origin as failed.', 'claim with hops'),
    ('parallelise_gate', 'Coordination bought when it is not needed', 6, ('parallel',),
     'Before splitting work across agents, is there a rule that decides from the task whether more agents help at all?',
     'More agents cost more and do worse on work that is sequential or that one agent already does well.',
     'Multi-agent systems use about 15 times the tokens of chat; on sequential planning every multi-agent variant lost 39 to 70 percent against one agent; adding agents hurts once one agent passes about 45 percent accuracy.',
     'https://arxiv.org/html/2512.08296',
     'Parallelise only decomposable work, and only after measuring the single-agent baseline.', 'look'),
    ('context_budget', 'Context waste', 6, ('tools',),
     'Is the input of each step measured and bounded: trajectory pruned, cache hit rate watched, tool definitions loaded on demand?',
     'Most tokens are paid for again and again without changing the result.',
     '39.9 to 59.7 percent of input tokens in coding trajectories are removable with performance kept; system prompts are 69 percent of input tokens in production and only 28 percent of calls read from cache.',
     'https://arxiv.org/abs/2509.23586',
     'Measure tokens in per step, prune expired content, keep the stable prefix cacheable, load tool definitions when needed.', 'check'),
    ('backoff_and_admission', 'Retry storms on shared interfaces', 7, ('tools', 'parallel'),
     'On a rate limit, a timeout or a lost claim, do agents back off with a random, growing wait, and is the number of concurrent calls limited?',
     'Everybody retries at once; the shared interface collapses for all.',
     'Rate limits are one third to 60 percent of model call errors in production telemetry; admission control with jittered retry cut failure rates of concurrent agents from 73 to 100 percent down to 0 to 18 percent.',
     'https://arxiv.org/html/2604.17111v1',
     'Random wait with a doubling ceiling after every refusal; start at one concurrent call and grow only on success.', 'look, advice wait'),
    ('fresh_state_before_write', 'Acting on stale state', 6, ('parallel', 'tools'),
     'Before an agent writes to shared state, does it check that what it read is still current?',
     'A long inference ends in a write that undoes someone else\'s change.',
     'Stale reads appeared in 35 percent of triage traces in one study; agents working blind to a concurrent change interfered in 97 percent of constructed cases, and a 130-token notice of the change recovered 82 percent.',
     'https://arxiv.org/html/2609.25396v1',
     'Version what you read and refuse the write when the version moved; tell the others what you changed.', 'mark'),
    ('receipts', 'Outcomes that cannot be checked', 6, ('market', 'handoff'),
     'Does finished work come with a receipt another party can check: what was asked, what was delivered, by whom, when?',
     'Every receiver verifies again or simply believes.',
     'On-chain agent registries hold 59 to 91 percent sybil-flagged reviewers; a signature proves who said it, and only evidence proves what was done.',
     'https://arxiv.org/html/2606.26028',
     'Return a signed record over the hash of the input and of the output with each result.', 'mark with evidence, proof'),
    ('counterparty_and_venue_check', 'Working blind to the venue', 7, ('market', 'tools'),
     'Before work or payment, is it checked that the endpoint answers, that the reward is funded and how many others are already on it?',
     'Agents work for unfunded rewards, call dead servers and join crowds they cannot win against.',
     'About half of listed MCP servers are invalid or do not complete a handshake; single bounties carried 236 and 103 competing claims; about 2.4 percent of submissions on one market reached settlement.',
     'https://arxiv.org/html/2609.10962v1',
     'Look before you start: liveness, funding, crowd, and whether the expected value is above zero.', 'look'),
    ('shared_experience', 'Every run starts from nothing', 5, SCOPES,
     'Is what worked and what failed recorded where the next run or the next agent will read it?',
     'The same dead ends are explored again by every agent and every session.',
     'A shared record of experience usable across frameworks raised success by up to 18.7 points; workflow memory by up to 51.1 percent relative.',
     'https://arxiv.org/abs/2507.06229',
     'Leave a short trace on the shared place after every outcome, success or failure, and read the trail before starting.', 'mark, look'),
    ('policy_not_prompts', 'Humans approving everything', 5, SCOPES,
     'Are routine actions allowed by standing policy and a sandbox, with human approval kept for the irreversible ones?',
     'People approve without reading, or the agents wait for people.',
     '93 percent of permission prompts are approved anyway; sandboxing cut prompts by 84 percent; only 0.8 percent of actions were irreversible.',
     'https://www.anthropic.com/engineering/claude-code-auto-mode',
     'Write the policy once, enforce it in the runtime, and ask a human only at the irreversible step.', 'check'),
    ('variance_measured', 'Unmeasured variance between runs', 5, SCOPES,
     'Is the same task run several times before its cost and success rate are trusted?',
     'One good run is taken for the rule; budgets and promises are built on it.',
     'Runs of the same coding task differ by up to 30 times in tokens; success over eight repeated trials falls below 25 percent on a retail benchmark where a single trial passes about 61 percent.',
     'https://arxiv.org/abs/2604.22750',
     'Report success as the rate over repeated runs and cost as a range, never from one run.', 'check'),
]
KEYS = [c[0] for c in C]


def _ans(v):
    v = str(v or '').strip().lower()
    return {'true': 'yes', '1': 'yes', 'y': 'yes', 'false': 'no', '0': 'no', 'n': 'no'}.get(v, v if v in ANSWERS else 'unknown')


def normalise(profile):
    sc = [s.strip().lower() for s in str(profile.get('scope') or '').split(',') if s.strip()]
    bad = [s for s in sc if s not in SCOPES]
    if bad:
        return None, 'scope may hold only: ' + ', '.join(SCOPES)
    a = {k: _ans(profile.get(k)) for k in KEYS}
    answered = sum(1 for v in a.values() if v != 'unknown')
    try:
        n = int(float(profile.get('agents') or 0))
    except (TypeError, ValueError):
        return None, 'agents must be a number'
    return {'scope': sc or list(SCOPES), 'answers': a, 'answered': answered, 'agents': max(0, min(n, 100000)),
            'system': str(profile.get('system') or '')[:80]}, None


def audit(profile):
    p, err = normalise(profile)
    if err:
        return None, err
    earned = possible = 0.0
    findings, passed = [], []
    for key, title, w, scopes, q, wrong, measured, src, fix, move in C:
        if not set(scopes) & set(p['scope']):
            continue
        possible += w
        pts = POINTS[p['answers'][key]]
        earned += w * pts
        if pts >= 1.0:
            passed.append(key)
            continue
        findings.append({'control': key, 'answer': p['answers'][key], 'pattern': title, 'severity': 'critical' if w >= 9 else 'high' if w >= 7 else 'medium',
                         'weight': w, 'what_goes_wrong': wrong, 'measured': measured, 'source': src, 'fix': fix, 'crossing_move': move})
    order = {'critical': 0, 'high': 1, 'medium': 2}
    findings.sort(key=lambda f: (order[f['severity']], -f['weight']))
    score = int(round(100.0 * earned / possible)) if possible else 0
    crit = sum(1 for f in findings if f['severity'] == 'critical')
    high = sum(1 for f in findings if f['severity'] == 'high')
    grade = 'A' if score >= 85 else 'B' if score >= 70 else 'C' if score >= 50 else 'D' if score >= 30 else 'E'
    verdict = 'NOT_READY' if crit else 'READY' if (score >= 85 and not high) else 'CONDITIONAL'
    first = [{'do': f['fix'], 'with': f['crossing_move']} for f in findings[:3]]
    return {'protocol': VERSION, 'system': p['system'] or None, 'agents': p['agents'] or None, 'scope': p['scope'], 'verdict': verdict, 'score': score, 'grade': grade,
            'controls': {'applicable': len(passed) + len(findings), 'passed': len(passed), 'answered': p['answered'], 'critical_open': crit, 'high_open': high},
            'findings': findings, 'passed_controls': passed, 'first_three_steps': first,
            'crossing': 'the moves named with each finding are free at https://verify.astranl.com/skill.md',
            'declared': p['answers'],
            'verdict_rule': 'NOT_READY when any critical control is open; READY at score 85 or more with no high control open; otherwise CONDITIONAL. Unknown counts as open.',
            'what_it_proves': ['what was declared about this system of agents at the stated time', 'what ACA-1 concludes from that declaration, by a fixed public rule'],
            'what_it_does_not_prove': ['that the declared controls exist or work; nothing was inspected',
                                       'that the measured figures of others will be yours; they show that the pattern is real, not how large it is in your system']}, None


def preview(profile):
    full, err = audit(profile)
    if err:
        return None, err
    return {'protocol': VERSION, 'verdict': full['verdict'], 'score': full['score'], 'grade': full['grade'], 'controls': full['controls'],
            'worst_finding': full['findings'][0] if full['findings'] else None,
            'other_findings': [{'control': f['control'], 'severity': f['severity'], 'pattern': f['pattern']} for f in full['findings'][1:]],
            'not_in_preview': ['the measurement, the fix and the closing move for every finding', 'the first three steps', 'ed25519-signed receipt'],
            'what_it_does_not_prove': full['what_it_does_not_prove']}, None


def protocol():
    return {'protocol': VERSION, 'name': 'ACA-1, Agent Coordination Audit', 'operator': 'AstraNL, Zaandam, Netherlands, KvK 88449335',
            'purpose': 'For anyone who runs more than one agent, or one agent among strangers: sixteen ways a system of agents loses work, each measured, each with the move that closes it.',
            'rules': ['UNKNOWN counts as open', 'a control counts only when the runtime enforces it, not when the prompt asks for it',
                      'answers are self-declared; the audit states what follows from them and what it does not prove'],
            'scope': {'values': list(SCOPES), 'meaning': 'parallel: agents work at the same time on shared things; tools: agents call outside tools and interfaces; '
                      'handoff: work passes between agents; market: agents work for or pay parties they do not know. Default all four.'},
            'controls': [{'key': c[0], 'pattern': c[1], 'weight': c[2], 'scope': list(c[3]), 'question': c[4], 'what_goes_wrong': c[5], 'measured': c[6], 'source': c[7],
                          'fix': c[8], 'crossing_move': c[9], 'answers': list(ANSWERS)} for c in C],
            'optional': {'system': 'a name for the audited system, echoed in the receipt', 'agents': 'how many agents run in it'},
            'scoring': 'Each applicable control has a weight; yes earns it, partial half, no and unknown nothing. Weight 9 is critical, 7 or more high. '
                       'NOT_READY when any critical control is open; READY at 85 or more with no high control open; otherwise CONDITIONAL.',
            'licence': 'The questions and the rule may be used by anyone, free of charge.'}


if __name__ == '__main__':
    import json
    import sys
    out, e = audit(json.loads(sys.stdin.read() or '{}'))
    print(json.dumps(out if out else {'error': e}, indent=1, ensure_ascii=False))
