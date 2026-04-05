---
name: glean-review
description: Review delivered glean fragments interactively - star, archive, or trash each one, capture a short note on why, feeds signals into feedback.jsonl
allowed-tools: Bash, Read, Edit
user-invocable: true
---

# glean-review

Walk the user through their inbox of newly delivered story fragments. Capture star/archive/trash decisions plus an optional note. This feeds future auto-tuning.

## Steps

1. Fetch the review queue. The worker prints a JSON array of inbox fragments (status: `inbox`, sorted by `captured` desc):

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m glean.worker --review
   ```

   Each item should include at minimum: `fragment_id`, `path` (absolute), `title`, `project`, `captured`, `draft_angle` (from the `## Thread` section), and an `excerpt` (first paragraph of `## What happened` or similar).

2. If the array is empty, print `Inbox is empty. Nothing to review.` and exit.

3. Initialize tallies: `starred=0, archived=0, trashed=0, skipped=0`. Track `remaining = len(items)`.

4. For each fragment, display a compact card:

   ```
   [i/N]  {title}
   project:  {project}          captured: {captured}
   thread:   {draft_angle}

   {excerpt}

   path: {path}
   ```

5. Ask the user with AskUserQuestion:
   - question: "What do you want to do with this fragment?"
   - options: `Star`, `Archive`, `Trash`, `Skip`, `Quit`

6. If the action is `Star` or `Trash`, ask a follow-up via AskUserQuestion for a one-line note on WHY (especially important for trash). Allow an empty note. Skip the note prompt for `Archive` and `Skip` unless the user wants to add one.

7. Apply the decision:

   a. Update the fragment file's frontmatter `status` field using Edit:
      - `Star` -> `status: starred`
      - `Archive` -> `status: archived`
      - `Trash` -> `status: trashed`
      - `Skip` -> leave as `inbox`, do not write feedback

   b. Append a feedback entry to `${CLAUDE_PLUGIN_DATA}/feedback.jsonl` (one line, JSON):
      ```json
      {"fragment_id": "...", "action": "star|archive|trash", "note": "...", "timestamp": "<ISO-8601 UTC>"}
      ```
      Prefer calling the worker if it exposes a feedback-writing subcommand; otherwise append directly with a shell heredoc. NOTE: CONTRACTS.md does not specify a dedicated feedback CLI flag - if none exists, append via shell and say so clearly in a comment to the user.

8. After each decision, print the running tally and remaining count:

   ```
   tally: * {starred} starred  | = {archived} archived  | x {trashed} trashed  | - {skipped} skipped  | remaining: {remaining}
   ```

9. If the user picks `Quit`, stop immediately, print a final summary, and exit. Do not process remaining items.

10. After the loop ends (all reviewed or user quit), print a final summary:

    ```
    glean-review session summary
    ----------------------------
    reviewed: N   starred: N   archived: N   trashed: N   skipped: N
    feedback written to: ${CLAUDE_PLUGIN_DATA}/feedback.jsonl
    ```

## Notes

- Do not batch-apply. One fragment at a time, wait for user input.
- Never delete fragment files. `Trash` only changes the frontmatter `status`.
- If Edit fails on a fragment (file moved, frontmatter malformed), surface the error, do NOT write a feedback entry for that item, and continue to the next.
- Timestamps must be UTC ISO-8601 with `Z` suffix.
