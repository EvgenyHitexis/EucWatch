# Issue tracker: GitHub

Issues and specs live in EvgenyHitexis/EucWatch on GitHub. Use the `gh` CLI from this repository; it infers the repository from the Git remote.

## Existing issue structure

- **#1 is the wayfinder map.** Its research/grilling/task children are native sub-issues (`gh api repos/EvgenyHitexis/EucWatch/issues/1/sub_issues --jq '[.[].number]'`).
- **Specs (#17, #43) link their implementation tickets through the body, not native sub-issues.** Each ticket starts with `## Parent` + the spec URL and has a `## Blocked by` section ("None (can start immediately)." or issue links). Write new spec tickets the same way.
- **Claim work by assigning EvgenyHitexis before starting it.**
- Decision authority is usually a specific issue comment (e.g. `issues/39#issuecomment-…`); cite the comment link, not just the issue.

## Conventions

For multiline bodies, write the exact text to a temporary file and pass it with `--body-file`.

- **Create an issue**: `gh issue create --title "..." --body-file <path>`
- **Read an issue**: `gh issue view <number> --comments`, or structured: `gh issue view <number> --json number,title,body,labels,comments`
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Make an issue a sub-issue of a parent**: the local `gh` is 2.46, which predates `--parent`/`--add-sub-issue` (2.94+). Use `gh api --method POST repos/EvgenyHitexis/EucWatch/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>` (database id, as in **Blocking** below). If that fails, put `Part of #<parent>` at the top of the child body.
- **Comment on an issue**: `gh issue comment <number> --body-file <path>`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh api --paginate 'repos/{owner}/{repo}/pulls?state=open' --jq '.[] | select(.author_association | IN("OWNER","MEMBER","COLLABORATOR") | not) | {number, title, author: .user.login, author_association, labels: [.labels[].name]}'`.
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Read the issue and its comments, as in **Read an issue** above.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (see **Make an issue a sub-issue of a parent**). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/EvgenyHitexis/EucWatch/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/EvgenyHitexis/EucWatch/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --body-file <path>`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
