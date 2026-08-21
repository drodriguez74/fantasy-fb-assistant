---
name: optimize-prompt
description: Optimizes raw or informal user prompts for execution with Claude Code / Claude CLI, agentic fan-out workflows, and multi-agent task execution.
---

# Prompt Optimizer for Claude Code & Agentic Workflows

When the user provides a raw prompt, draft request, or task instruction intended for Claude Code, transform it into a highly structured, battle-tested prompt optimized for terminal execution, sub-agent delegation, and automated state tracking.

## Optimization Blueprint

Every optimized prompt must incorporate the following elements:

1. **Context & Source Grounding**
   - Explicitly state where inputs come from (e.g., current workspace context, specific files, audit documents, or git status).

2. **Structured Task Breakdown**
   - Require a Markdown checklist (`- [ ]`) grouped by priority (Immediate, Near-Term, Long-Term) or component area.
   - Force items to be actionable and precise.

3. **Sub-Agent Delegation Protocol**
   - Define clear boundaries for sub-agents (e.g., parallel vs. sequential execution based on file dependencies).
   - Require sub-agents to update task checkboxes (`- [x]`) upon completion to prevent duplicate work and retain execution state.

4. **Verification & Deliverable Definition**
   - Require a final summary reporting modified files, completed items, and any unresolved blockers.

---

## Output Format

When generating the optimized prompt for the user, present:
1. **The Recommended Prompt** (inside a copyable code block).
2. **A Concise Prompt Variant** (for quick interactive sessions).
3. **Key Enhancements Applied** (bullet points explaining what was fixed or added).

---

## Instructions for the Assistant

1. Fix all typos, colloquialisms, and missing technical context.
2. If the user mentions "fan out", "sub-agents", or "delegation", explicitly include file locks or dependency ordering instructions so agents don't overwrite each other's code.
3. Keep the prompt actionable, direct, and free of vague meta-instructions.