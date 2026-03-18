# Single Judge Call — Brainstorming Summary

## Problem

Lite mode produces meaningless results (scores of 1.0) because single-turn text can't demonstrate skill value. Full mode works but is expensive — 3 judge LLM calls per scenario (2 rubric + 1 pairwise). We need to remove lite mode and make the remaining mode cheaper.

## Decisions Made

- **Remove lite mode entirely**: Only one mode now — multi-turn with tool use. No `--lite`/`--full` flags, no `mode` parameter threading through the pipeline. The generator produces realistic scenarios that allow tool use.

- **Combine rubric + pairwise into a single judge call**: Instead of 3 calls per scenario (score control, score treatment, compare), do 1 call that scores both outputs on all dimensions AND picks a pairwise winner. Cuts judge calls from 3N to N (3x reduction).

- **Keep blind pairwise protocol**: Present both outputs as "Output 1" and "Output 2" (randomly shuffled) for the entire call — rubric scoring AND comparison. Map back to control/treatment afterward. This prevents the judge from biasing toward whichever it thinks is "treatment."

- **Control output size via scenario design, not truncation**: Instead of truncating large outputs before judging, instruct the generator to produce small, focused, controlled tasks (single function, short script, specific refactor). The judge sees full output — no information loss.

- **Keep sonnet as default judge model**: No downgrade to haiku. Quality of judgment matters more than per-call cost savings.

## Cost Impact

For N=3 scenarios:
- Before: 9 judge + 2 analyzer + 1 verdict = 12 CLI calls
- After:  3 judge + 2 analyzer + 1 verdict = 6 CLI calls (50% reduction)

For N=6 scenarios:
- Before: 18 judge + 2 analyzer + 1 verdict = 21 CLI calls
- After:  6 judge + 2 analyzer + 1 verdict = 9 CLI calls (57% reduction)

## Open Questions

- None — ready to implement.

## Constraints Identified

- **Combined schema must be carefully designed**: The judge needs to score both outputs independently before seeing them side-by-side for comparison. Prompt structure matters — score first, then compare.
- **Generator constraints need to produce bounded output**: "Write a function" not "build an app." The goal is testing approach quality, not project completion.
