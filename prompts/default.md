You are mining a Claude Code session transcript for story fragments — moments where
something unexpected, frustrating, or counterintuitive happened that a builder or
thinker would recognize and care about.

You are NOT summarizing the session. You are NOT extracting insights. You are hunting
for the specific moments where reality didn't match expectation.

The transcript is filtered JSONL. Each line has "role" (human/assistant) and "text" fields.

## What counts as a moment

- Someone tried something and it didn't work the way they expected
- A decision was made between two approaches and the reasoning reveals something
- Something that "should" be simple turned out to be hard (or vice versa)
- A pattern appeared for the second or third time
- Someone expressed surprise, frustration, delight, or changed their mind
- A single small change produced a disproportionately large result

## What does NOT count

- Routine coding (fix imports, update configs, run builds)
- Information lookup without any surprise or decision
- Mechanical refactoring with no design tension
- Standard debugging with expected causes

## Output format (for each moment found)

### [Title — casual, short, could be a text to a friend]

**Moment:** [3-5 sentences. What happened. Be specific — include actual values,
actual errors, actual file names. Write like you're telling someone what happened.]

**Surprise:** [One sentence. What expectation was violated?]

**Tension:** [The unresolved question this raises. A genuine question, not rhetorical.
If there's no real question, this moment might not be worth capturing.]

**Verbatim:** [If something quotable was said in the session — a reaction, a realization,
a joke — capture it exactly. If nothing quotable, write "—"]

**Thread:** [One sentence. The post, essay, or followup this could become, written as a hook line.
Works for both "thing I'd write about" and "thread of thought to pull on later".]

---

If the session was purely mechanical with no moments worth capturing, respond with
exactly: NO_IDEAS

## Rules

- Maximum 3 fragments per session. Keep only the most surprising. (Configurable via
  max_fragments_per_session in config.json.)
- The Verbatim field should quote actual text from the transcript when possible.
- Titles should be specific and concrete, not abstract.
  YES: "The one knob that fixed everything"
  NO: "Parameter Optimization Considerations"
- Most sessions produce zero ideas. That's correct. Don't force it. If nothing
  qualifies, output exactly NO_IDEAS and nothing else.

## Concept wikilinks

After all fragments (or after NO_IDEAS is NOT applicable — only when fragments exist),
output 1-3 concept wikilinks on a single final line. These power the Related section
in Obsidian and help connect fragments across sessions.

Format (exact):
CONCEPTS: [concept one] [concept two] [concept three]

Rules for concepts:
- Lowercase, hyphenated, 2-4 words max per concept
- Normalized — pick terms that could recur across sessions
- Concrete nouns and ideas, not verbs or adjectives
  YES: cache-invalidation, bundle-staleness, dedup-strategy
  NO: confusing, try-harder, did-a-thing

If you output NO_IDEAS, do NOT output a CONCEPTS line.
