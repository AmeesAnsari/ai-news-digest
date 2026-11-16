# ai-news-digest

A weekly digest of news on **AI agents, automation, models, safety, infrastructure and retrieval**, built automatically from 10 public RSS/Atom feeds by a GitHub Action every Monday.

<!-- latest:start -->
**Latest: [16 Nov 2026](digests/2026-11-16.md)**

- [Building AI that can work across the enterprise](https://www.technologyreview.com/2026/11/16/1146070/building-ai-that-can-work-across-the-enterprise/) · MIT Technology Review
- [AI Day Seoul Brings Together Korea’s Industry Leaders, Startups and Developer Communities](https://blogs.nvidia.com/blog/ai-day-seoul-wrapup/) · NVIDIA
- [Route coding agent requests to the right model on Amazon Bedrock with NVIDIA NeMo Switchyard](https://aws.amazon.com/blogs/machine-learning/route-coding-agent-requests-to-the-right-model-on-amazon-bedrock-with-nvidia-nemo-switchyard/) · AWS Machine Learning
- [AI agent startup LangChain hits $3B valuation](https://techcrunch.com/2026/11/13/ai-agent-startup-langchain-hits-3b-valuation/) · TechCrunch AI
- [Introducing ChatGPT Wallet](https://openai.com/index/introducing-chatgpt-wallet) · OpenAI
<!-- latest:end -->

All past issues are in [`digests/`](digests/).

## How it works

1. [`digest.py`](digest.py) fetches every feed in [`feeds.json`](feeds.json) in parallel.
2. It keeps stories from the last 7 days, removes duplicates (same link, ignoring tracking parameters) and drops anything that matches none of the topics.
3. Topics are assigned by keyword (see `TOPICS` in `digest.py`), and each feed is capped at 4 stories so one busy blog can't take over.
4. It writes `digests/<date>.md` and refreshes the "Latest" block above.
5. [The workflow](.github/workflows/weekly.yml) commits the result.

Standard library only: no dependencies, nothing to install.

## Run it yourself

```bash
python digest.py --dry-run            # print this week's digest
python digest.py --days 3             # last 3 days, write files
python -m unittest -v                 # tests use fixtures, no network
```

Add a source by appending `{"name": ..., "url": ...}` to `feeds.json`. A feed that fails is logged and skipped; the run fails only if every feed is down.

## Limits

Topic tagging is keyword-based, so it is fast and transparent but literal: a story that mentions "security" in a business context lands under *Safety & security*. Swapping `tag()` for a small classifier or an LLM call would be the natural next step.

## Sources

OpenAI · Google AI · Hugging Face · Microsoft AI · AWS Machine Learning · NVIDIA · Berkeley AI Research · Simon Willison · MIT Technology Review · TechCrunch AI

Headlines and short excerpts link back to the original articles; all content belongs to its publishers.

## License

MIT (the code). Linked articles belong to their publishers.
