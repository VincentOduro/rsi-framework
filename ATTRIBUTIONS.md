# Attributions & Inspirations

This framework draws on ideas from open-source projects, academic research,
and industry practitioners. No code was copied. Architecture patterns and
concepts were adapted to fit the RSI framework's Toyota Production System model.

## Core Inspiration

**Toyota Production System (TPS)**
The entire framework is built on Toyota's 14 management principles as
documented by Jeffrey Liker in "The Toyota Way" (2004, 2nd ed. 2021).
TPS concepts: Jidoka, Kaizen, Genchi Genbutsu, Heijunka, Hansei, Muda,
Nemawashi, Poka-yoke.

## Feature Inspirations

### Quality Ratchet (Phase 1)
**Inspired by:** [toryo](https://github.com/andyrewlee/awesome-agent-orchestrators)
An intelligent agent orchestrator with trust-based delegation and quality
ratcheting via git commit/revert. Adapted concept: checkpoint on verify pass,
revert on fail — quality only goes up.

### Compound Learning / Session Brief (Phase 2)
**Inspired by:** Addy Osmani's research on multi-agent coding patterns.
- [The Code Agent Orchestra](https://addyosmani.com/blog/code-agent-orchestra/)
- [How to write a good spec for AI agents](https://addyo.substack.com/p/how-to-write-a-good-spec-for-ai-agents)
- [My LLM coding workflow going into 2026](https://medium.com/@addyosmani/my-llm-coding-workflow-going-into-2026-52fe1681325e)

Adapted concept: AGENTS.md pattern — accumulate patterns and gotchas across
sessions, generate a session brief so every session starts better than the last.

### Parallel Delegation (Phase 3)
**Inspired by:** [ccswarm](https://github.com/nwiizo/ccswarm)
Multi-agent orchestration with Git worktree isolation for parallel development.
Adapted concept: independent subtasks run simultaneously via concurrent.futures.

### Task DAG / Dependency Resolution (Phase 4)
**Inspired by:** [OpenMultiAgent](https://github.com/JackChen-me/open-multi-agent)
TypeScript multi-agent engine with auto task decomposition and topological
dependency resolution. First-class MiniMax M2.7 support.
Adapted concept: `depends_on` field in task specs, layered parallel execution.

### Worker Trust Scoring (Phase 5)
**Inspired by:** [Orchestrator-Agent Trust](https://github.com/Applied-AI-Research-Lab/Orchestrator-Agent-Trust)
Research framework for trust-aware orchestration with confidence calibration
metrics (ECE, OCR, CCC). Published as academic paper.
Adapted concept: per-task-type accept rate tracking, auto-accept above
threshold with spot-checks.

### Declarative Rules Engine (Phase 6)
**Inspired by:** [AgentSpec](https://arxiv.org/abs/2503.18666) (ICSE 2026)
Customizable runtime enforcement for LLM agents via trigger-predicate-action
rules. Research paper presented at ICSE 2026, Rio de Janeiro.
Adapted concept: rules as YAML instead of hardcoded Python if-else chains.

## Additional References

- [Cognitive Scaffolding for Autonomous Agents](https://gist.github.com/LangSensei/ffece86d696948ef739e42233642141a) — hypothesis-prediction-test loop pattern
- [Awesome Agent Orchestrators](https://github.com/andyrewlee/awesome-agent-orchestrators) — curated list of orchestration tools
- [Awesome Self-Evolving Agents](https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents) — survey of self-evolving AI agents
- [Claude MPM](https://github.com/bobmatnyc/claude-mpm) — multi-channel orchestration for Claude

## License Compatibility

All inspirations are from open-source projects or published research.
No code was copied. Pattern adaptations are original implementations
written specifically for the RSI framework.
