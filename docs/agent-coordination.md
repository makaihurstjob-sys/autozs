# Parallel work protocol

## Assignment and isolation

The coordinator records task, owner, base commit, branch, worktree, permitted files, acceptance checks, and status in docs/agent-board.md before dispatch. Workers must receive an explicit assignment; an empty worktree is not a running agent.

Use one branch and worktree per active worker under C:/AutoZS/worktrees. Every shell command must target the assigned checkout explicitly. Worktrees share Git metadata and the host: never assume databases, ports, browser profiles, services, or credentials are isolated.

Workers may read code and run isolated tests. Do not load production .env files, start application servers/workers, use operational databases, navigate operational browser tabs, reload extensions, or change live policies without a coordinator assignment for that resource. Tests must use disposable databases and mocks; inspect their setup before running. Do not copy credentials or database files into worktrees or commit them.

## Shared state

PROJECT_CONTEXT.md is the versioned baseline. C:/AutoZS/repo/docs/agent-board.md is the canonical local assignment board; copies in worker branches can be stale. Only the coordinator writes the board. Workers read it at start and before handoff and communicate blockers through their parent session. This protocol also applies to separately launched Claude/Codex sessions; they must be registered on the board before working.

Runtime resources (operational Chrome, delivery Chrome, AUTOZS API/service and database) belong to the coordinator by default. No worker currently holds a live-resource grant. A grant must name the resource, owner, operation and end condition on the board. On interruption, assume the resource remains occupied until checked; do not automatically steal ownership. Markdown records coordination, not an enforced process lock.

## Handoff and serial integration

Workers report findings, changed files, base and result commits, exact test commands/results, limitations and follow-up. Commit only assigned files; never stage everything. The coordinator reviews each diff, checks for overlapping changes and pre-existing work, then cherry-picks one result at a time and runs appropriate checks on the combined tree. Conflicts are resolved by the coordinator, not by overwriting another branch.

Do not reset, clean, switch or stash someone else's checkout. Keep worktrees until their results are integrated or deliberately retained. Live activation follows separate idle/resource checks and existing user authorization. Do not equate passing mocked tests with live validation.

## Resume

On a new session, inspect git status and worktree list, read the canonical board, and verify whether listed agents still exist. A persisted 'running' row is not evidence of a living process. Reconcile interrupted work before reassigning it. 'Continue' authorizes the next useful work within the project scope; ask only for missing decisions or information that blocks safe progress.
