# Learning File Template

Use this format when writing learnings to `.claude/learnings/`.
Always write both the learning file AND an entry in `index.yaml` atomically.

## File format

```yaml
---
title: [Short descriptive title]
tags: []
severity: low
date: YYYY-MM-DD
---

## Problem

[What went wrong or what was discovered]

## Solution

[What fixed it or what the correct approach is]

## Prevention

[How to avoid this in the future]
```

## index.yaml entry format

```yaml
- file: [filename].md
  triggers: "keyword1 keyword2 keyword3"
```

Triggers should be words that would appear in a user's prompt when this learning is relevant.
The UserPromptSubmit hook matches prompts against these keywords (minimum 2 word matches to surface).
