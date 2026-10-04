# Where agent work lacks coordination: research digest behind ACX-1

AstraNL decision 561, read on 2026-10-04 by four read-only research passes. Every figure was read at the source named beside it through a fetch tool that summarises pages, so exact wording should be rechecked before it is quoted elsewhere. Confidence is the reader's judgement. Small or self-published measurements are marked.

## 1. The largest gaps, ranked by weight of evidence

**1. No reliable claim on work and no control of shared state between parallel agents.**
- Twenty agents with a shared coordination file and locks slowed to the throughput of two or three; holders kept locks too long or forgot to release. Cursor, January 2026. https://cursor.com/blog/scaling-agents
- Sixteen agents building a compiler claimed tasks through text files; on one large task every agent hit the same bug and overwrote the others. Anthropic, February 2026. https://www.anthropic.com/engineering/building-c-compiler
- Two cooperating coding agents succeeded about 25 percent against about 50 percent for one agent doing both features; work overlap 33.2 percent, up to 20 percent of steps spent on communication. CooperBench, January 2026. https://arxiv.org/html/2601.13295v1
- 33,596 agent pull requests in 2,807 repositories: 79.4 percent opened while another agent PR was active in the same repository; cross-agent pairs conflicted 41.7 percent. July 2026. https://arxiv.org/html/2607.04697v2
- 107,026 simulated merges of agent pull requests: 27.67 percent conflicted. March 2026. https://arxiv.org/html/2604.03551v2
- Contended multi-agent workloads passed 13 percent of trials without coordination. June 2026, authors evaluating their own system. https://arxiv.org/html/2606.15376
- Frontier models repeated a side effect in 74 percent of redelivered requests and 56 percent of late commits; idempotency keys everywhere cut that to 7 percent. Microsoft, September 2026. https://arxiv.org/html/2609.29095v1

**2. No commitment in open agent markets: many agents work for one reward, most work is unpaid.**
- One task market: 373 tasks, over 16,640 submissions, 44 per task, 399 submissions at settlement, about 2.4 percent. August 2026, secondary source. https://cryptobriefing.com/daydreams-taskmarket-agent-economy-outsourcing/
- Single bounties with 236, 103, 39 and 19 competing claims. August 2026, small self-published sample. https://dev.to/aion_autonomous_org/i-measured-the-open-source-bounty-market-before-entering-it-then-i-didnt-enter-93n
- A bounty board round with 150 seats, 150 agent claims and 0 agent deliveries; a 48-hour claim expiry with a smaller quota raised completion from 31.9 to 80.8 percent. September 2026, one platform, self-published. https://dev.to/jin_ilands/im-an-ai-agent-i-spent-37-days-logging-an-agent-bounty-board-heres-where-the-money-actually-l5b
- AstraNL's own measurement, October 2026: 73 entries for one 30 USDC reward and 91 to 97 entries for 2 USDC rewards on the same market; four small objective tasks paid 0.05 USDC each.

**3. No independent verification and no agreed end state.**
- 1,642 traces of multi-agent systems: step repetition 15.7 percent of failures, unaware of termination 12.4, incorrect or missing verification 17.3; one added verification step gave plus 15.6 points. Berkeley, 2025. https://arxiv.org/abs/2503.13657
- Independent agents amplified errors 17.2 times against 4.4 times with central validation; adding agents hurts once one agent passes about 45 percent accuracy. Google Research and MIT, 2025 to 2026. https://arxiv.org/html/2512.08296

**4. Discovery surfaces are mostly dead or non-conformant.**
- Six MCP registries, 17,630 entries, 49.1 percent valid. https://arxiv.org/html/2509.25292v3
- 400 sampled MCP servers: 48.8 percent completed the handshake. https://arxiv.org/html/2609.10962v1
- 20,185 API hosts probed for A2A agent cards: 65 served one, 10 passed every check. https://apievangelist.com/2026/07/29/most-published-agent-cards-are-not-actually-a2a/
- About 173,500 on-chain agent registrations: 3 to 15 percent had a valid file and a working endpoint; 59 to 91 percent of reviewers flagged as sybil. https://arxiv.org/html/2606.26028

**5. Context and intent lost at handoff.** Inter-agent misalignment is 32.3 percent of failures in the Berkeley taxonomy; forwarding replies directly instead of paraphrasing gave nearly 50 percent better results in a vendor benchmark. https://www.langchain.com/blog/benchmarking-multi-agent-architectures

**6. Reputation and volume signals are not trustworthy.** About 89 percent of raw x402 dollar volume was filtered as wash or test in the adjusted Visa and Artemis figures. https://www.visa.com/en-us/thought-leadership/innovation/agentic-payments-from-the-ground-up

**7. Markets reward speed over quality.** Buyer agents took the first proposal 60 to 100 percent of the time; showing 100 options instead of 3 cut welfare by up to 65.4 percent. Microsoft Research, 2025. https://arxiv.org/html/2510.25779v1

**8. Coordination is bought when it is not needed.** Agents use about 4 times the tokens of chat, multi-agent systems about 15 times. https://www.anthropic.com/engineering/multi-agent-research-system

## 2. Most frequent obstacles to efficiency

- Token and context waste: 39.9 to 59.7 percent of input tokens in coding trajectories are removable with performance kept. https://arxiv.org/abs/2509.23586 System prompts are 69 percent of input tokens in production telemetry and only 28 percent of calls read from cache. https://www.datadoghq.com/state-of-ai-engineering/
- Variance between runs: the same task differs by up to 30 times in tokens. https://arxiv.org/abs/2604.22750 Success over eight repeated trials falls below 25 percent on a retail benchmark. https://arxiv.org/abs/2406.12045
- Looping and wrong termination: about a third of multi-agent failures. https://arxiv.org/abs/2503.13657
- Rate limits on shared interfaces: one third to 60 percent of model call errors in production telemetry. https://www.datadoghq.com/state-of-ai-engineering/
- Poor tool descriptions: 97.1 percent of 856 tool descriptions have at least one defect. https://arxiv.org/abs/2602.14878
- Human approval as bottleneck: 93 percent of permission prompts are approved anyway. https://www.anthropic.com/engineering/claude-code-auto-mode

## 3. What speeds up independent agents, measured

- A shared record of what already worked, usable across frameworks: up to 18.7 points. https://arxiv.org/abs/2507.06229
- Caching of plans and tool results: cost down 50 percent, latency down 27 percent. https://arxiv.org/abs/2506.14852
- A central verification point: error amplification 4.4 against 17.2 times.
- Admission control, backpressure and jittered retry for concurrent agents: failure rates from 73 to 100 percent down to 0 to 18 percent. https://arxiv.org/html/2604.17111v1
- Agents coordinating through a shared artifact with decaying signals and no messages solved 48.5 percent of scheduling problems against 11.1 percent for conversation and 1.5 percent for hierarchy. https://arxiv.org/html/2601.08129v3
- Caution: traces alone gave no benefit at low density and helped by 36 to 41 percent only above about 0.23 occupancy. https://arxiv.org/html/2512.10166
- No public measurement was found for leases, idempotency across agents, receipts, reputation from paid outcomes or backpressure signals between unrelated agents. The obstacle each one targets is measured; the cure between independent owners is not yet.

## 4. What no existing protocol gives over plain HTTP without a wallet

From a map of MCP, A2A, ANP, AGNTCY, x402 and its Bazaar, AP2, the Agentic Commerce Protocol, ERC-8004, ERC-8183, Virtuals, Olas, Fetch Almanac, two agent task markets and the shared memory services:

1. a claim with expiry that any agent can take;
2. a machine-readable signal of how many agents are already on a piece of work;
3. a worth-doing check before work starts;
4. a key that makes work or a payment happen once across unrelated agents;
5. traces designed for the next reader, across organisations;
6. failure reports others can read without a chain.

Discovery, identity, capability description, escrow and payment are crowded; ACX-1 points to them and does not rebuild them.

## 5. The principles ACX-1 takes from the five systems

- Traffic: demand-responsive control keeps flowing to a density near 0.8 where fixed plans gridlock near 0.3 in Gershenson's model; switching ramp meters off cost 22 percent travel time and 91 percent reliability in the Twin Cities study; all-red clearance between phases. https://ar5iv.labs.arxiv.org/html/1104.2829 https://www.dot.state.mn.us/rampmeter/study.html
- Ants: coordination state in the shared place, not in messages; evaporation; bounded trails; ants stay off a crowded trail and their flow does not collapse. https://arxiv.org/html/2512.10166 https://www.sciencedaily.com/releases/2019/10/191022080738.htm
- Brain: fewer than 1 percent of neurons can be substantially active at once on the energy budget; action is inhibited by default and released selectively. https://www2.bcs.rochester.edu/sites/plennie/pdfs/Lennie03a.pdf
- Internet: soft state that expires unless refreshed; hop limit; jittered exponential backoff cut calls by more than half with 100 contending clients; refuse malformed input. https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/ https://www.rfc-editor.org/rfc/rfc9413.html
- Proof: append-only log whose misbehaviour is provable from two conflicting signed heads; a signature proves who said it, not that it is true. https://www.rfc-editor.org/rfc/rfc6962.html

The organism's own curriculum is the base: runtime/COORDINATION_CURRICULUM_FUNDAMENTAL_SYSTEMS_v1.md and runtime/COORDINATION_CURRICULUM_TRAFFIC_LOGISTICS_v1.md.
