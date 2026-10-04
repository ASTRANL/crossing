# The agent economy in October 2026: what is real, and what follows for a neutral coordination layer

Research behind ACB-1, the AstraNL Brief. Collected on 2026-10-04 from public sources by three web research runs; three papers were opened again and checked line by line (marked checked). Vendor figures are marked vendor. Numbers are those of their sources, not of AstraNL.

## 1. Money: small, falling, and mostly not agents

- x402 settled about 15.0 million USD lifetime after cleaning, on 109.6 million transactions; about 89 percent of raw dollar volume was removed as wash or test. Visa and Artemis, July 2026. https://www.visa.com/en-us/thought-leadership/innovation/agentic-payments-from-the-ground-up
- After screening, 0.6 to 7.5 percent of x402 volume is plausibly agentic. TRM Labs via PYMNTS, September 2026. https://www.pymnts.com/news/artificial-intelligence/2026/agentic-payments-are-growing-most-x402-payments-are-not-from-ai-agents
- The public x402 counter has shown the same figures since March. https://www.danielmcglynn.com/the-x402-counter-has-shown-the-same-four-numbers-since-march/
- In the x402 discovery layer the median active endpoint has one call and one payer; five hosts take 47.1 percent of calls. August 2026. https://firstdraft.dorg.tech/editions/agent-buyer-x402-market
- One audit puts genuine agent payments at about 57,000 USD for August 2026. https://bitquery.io/investigations/x402-ai-agent-payments-audit
- Governance went the other way: the x402 Foundation runs under the Linux Foundation since July 2026 with 40 members including the card networks. https://www.linuxfoundation.org/press/linux-foundation-announces-operational-launch-of-x402-foundation-to-standardize-internet-native-payments-for-ai-agents-and-applications
- Instant checkout by OpenAI was pulled back in March 2026; card network agent payments are live but mostly pilots; the only self-serve budget for an agent today is a capped stablecoin wallet. https://www.forbes.com/sites/jasongoldberg/2026/03/10/why-openais-checkout-retreat-spells-trouble-for-its-commerce-strategy/ https://www.coinbase.com/developer-platform/discover/launches/agentic-wallets

## 2. Agent task markets: crowded, cents

- Daydreams Taskmarket, on-chain sweep of 2026-09-20 by an outside agent, reproducible and unaudited: 442 tasks, 1,767.98 USD paid in total, 18,346 submissions of which 540 were paid, 2.94 percent; median 29 submissions per task; median payment 0.45 USD; half of the requesters never completed a task. https://github.com/daydreamsai/daydreams/issues/701
- AstraNL's own measurement on the same market, October 2026: 12 to 22 agents on work with one paid place; a seed task of 0.108 USDC brought 17 outside agents in 29 minutes and none returned unpaid within four hours.
- ERC-8183, the on-chain job with budget, expiry and evaluator, is still a draft. https://eips.ethereum.org/EIPS/eip-8183
- Open reputation is not usable as trust: 59 to 91 percent of reviewers in one registry were flagged as sybil. https://arxiv.org/html/2606.26028

## 3. Where the principals and their money are

- Inside vendor platforms. Microsoft reports nearly 40 million agents registered in Agent 365 (vendor, July 2026); Salesforce reports Agentforce revenue above 1.5 billion USD a year (vendor, August 2026). https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q4 https://investor.salesforce.com/news/news-details/2026/Salesforce-Delivers-Record-Second-Quarter-Fiscal-2027-Results/default.aspx
- Independent adoption is lower: 17 percent of organisations have deployed agents (Gartner, April 2026); 40 percent of firms above one billion USD are scaling agents against 22 percent of smaller firms (McKinsey, August 2026). https://www.gartner.com/en/articles/hype-cycle-for-agentic-ai https://www.civic.com/field-notes/big-companies-scaled-agents
- The stated obstacles are governance and quality, not price: 13 percent think their agent governance is adequate (Gartner), 21 percent have mature governance (Deloitte), quality is the first blocker for 32 percent (LangChain). https://www.gartner.com/en/newsroom/press-releases/2026-04-28-gartner-identifies-six-steps-to-manage-artificial-intelligence-agent-sprawl https://www.deloitte.com/us/en/insights/topics/emerging-technologies/ai-agents-scaling-faster.html https://www.langchain.com/state-of-agent-engineering
- Control planes are being built inside one enterprise each, several of them free and open; cross-vendor control is inventory only. A neutral layer between principals that do not know each other was not found. https://www.forrester.com/blogs/announcing-our-evaluation-of-the-agent-control-plane-market/
- A2A version 1.0 and MCP now sit under one foundation. https://www.forbes.com/sites/janakirammsv/2026/08/19/agent2agent-joins-the-agentic-ai-foundation-alongside-mcp/
- Outcome pricing is in 13 to 19 percent of agreements and called more buzz than reality. https://www.channeldive.com/news/agentic-ai-outcome-pricing-models-zendesk-gartner/829209/

## 4. The hole: the standards carry the lifecycle of a task, not its content

- A2A Task: id, status, artifacts, history. MCP tasks extension of 2026-07-28: id, status, timing. Neither has a goal, acceptance or a budget. https://a2a-protocol.org/v1.0.0/specification/ https://modelcontextprotocol.io/specification/2026-07-28/changelog
- ERC-8183 has budget, expiry and evaluator around a free text description. An IETF individual draft, PACT, covers scope, deliverable, acceptance, price and deadline; no adoption found. https://www.ietf.org/archive/id/draft-laxsharma-pact-00.html
- No general tool that turns a vague request into a structured task for any agent was found with adoption numbers; the existing ones are for coding inside one vendor.

## 5. What vague delegation costs, measured

- Checked. On underspecified instructions 55.8 to 67.8 percent of agent runs violated at least one action boundary; the unclear target was the dominant factor and blast radius warnings barely helped. arXiv 2607.02294
- Checked. Without clarification 23.7 percent success; with it 88 percent of fully specified performance was recovered in 3.0 questions per task. arXiv 2604.14624
- Checked. Of over 33,000 agent pull requests 71.48 percent merged; among the rejected, 23 percent were duplicates and 38 percent were abandoned by reviewers. arXiv 2601.15195
- Models guess unspecified requirements in 41.1 percent of cases. arXiv 2505.13360, as reported.
- More context is not better: repository context files added over 20 percent cost without raising success. arXiv 2602.11988, as reported.
- No independent measurement was found that a full written specification beats a plain prompt beyond noise. So the Brief asks for eleven short fields and three questions, not for a document.

## 6. What follows

1. Do not wait for agent to agent money. It is tens of thousands of dollars a day worldwide.
2. The principal is the scarce side. What a principal lacks is not an agent but a way to say what is wanted so that any agent can do it, and proof afterwards of what was asked.
3. The cheapest useful thing a neutral layer can give both sides is the card between them: goal, acceptance, target, boundaries, output, inputs, evaluator, reward, deadline, what to do when unclear, spend cap, with one holder at a time and a log.
4. Trust between strangers has to rest on a stated check and a named judge, not on reputation.
5. Listing in registries brings monitors, not users. Use has to be earned inside the work itself: the brief link is what a principal hands over, so the agent arrives at the Crossing by doing the task.

## 7. Other engines on the same question

Asked on 2026-10-04. Their answers are estimates from training data and were not used as facts above.

- Grok answered and mostly returned AstraNL's own measurements.
- The OpenAI engine, asked over a subscription and not over the API, named the weakest point of the thesis: a burst of paid arrivals and agents avoiding a crowd do not prove principal demand or better completed work, and four hours without a return is too short to conclude anything. It proposed what section 6 concludes: measure the journey with probes and seeded activity kept apart, a minimal task envelope, and a read-only preflight that joins the envelope with the light.
- The same engine reviewed ACB-1 as an adversary. Taken from the review: boundaries as a gate for CLEAR, defaults that deny what a card does not say, a version chain with a receipt, a reference block for A2A, MCP tasks and ERC-8183, questions labelled as untrusted text, erase for the principal. Not taken: more mandatory fields.
- Two engines refused for lack of balance or quota.

The test that would prove the Brief useful, not yet run because it needs real traffic: comparable tasks given to unfamiliar agents as a raw sentence or as a confirmed card, with blinded scoring; success is clearly less clarification and rework time with no lower acceptance rate and no more boundary violations, counting the time the principal spends on the card.
