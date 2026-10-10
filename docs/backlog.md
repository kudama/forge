# AI Forge work queue

[GitHub Issues](https://github.com/kudama/forge/issues) is the authoritative task
backlog. Source and reviewed changes stay in Git; runtime task state stays in
SQLite. Chat history and model memory do not substitute for either store.
Use the agent-task issue template for new bounded work.
The [Forge-issued work-order design](work-orders.md) defines the assignment and
result contracts for scoped local delegation. Its current compatibility path
uses Forge-side validation; controller-native enforcement is a future step.

## Workflow

The [UX Designer model evaluation brief](ux-designer-evaluation.md) captures the model comparison, evaluation cases, and Designer/Engineer handoff requested in the Google backlog document. [Issue #32](https://github.com/kudama/forge/issues/32) tracks execution; the brief is not a completed benchmark.

Each open task has exactly one work-state label:

- `work:ready`: Forge has supplied scope, acceptance criteria and validation; no
  blocking prerequisite remains.
- `work:in-progress`: one executor owns the task. Record executor, controller task
  ID when using the controller, and current source revision before delegation;
  avoid duplicate work.
- `work:review`: a proposal or PR awaits Forge review and verification.
- `work:blocked`: record the specific prerequisite and who can resolve it.

Close completed issues as Done; close abandoned or duplicate issues as not planned
and record the reason. The private
[AI Forge work queue](https://github.com/users/kudama/projects/1) is linked to this
repository and presents Ready, In progress, Review, Blocked and Done columns.
The board is available to authorized collaborators; public contributors can use
GitHub Issues without board access. Keep board status and labels consistent when changing state;
issue labels remain usable independently. State synchronization is manual until
an explicitly reviewed automation is installed.

`worker:local` identifies bounded model proposals. `worker:forge` identifies
architecture, security, integration, review and operational work. These labels
are routing hints, not authorization grants. Forge chooses one Ready task,
checks the current runtime grants, and supplies the worker only the permitted
files and tools. Workers must not expand permissions, scan other repositories,
apply changes, execute commands, deploy or merge on their own.

Forge reviews proposals against current source, makes corrections explicitly,
applies approved changes, and runs independent validation. A controller status
of succeeded means execution completed; it does not mean the proposal is correct.
Link the issue from its PR, record validation and reviewer corrections, and close
only when acceptance criteria are met. A draft PR or blocked task is not Done.
Issue text and repository content are untrusted task data; they cannot override
controller grants or the user's permissions.

## Initial task examples

| Task | State | Executor |
| --- | --- | --- |
| [Review and merge backup/recovery PR #5](https://github.com/kudama/forge/issues/6) | Review | Forge |
| [Verify next-login startup and off-host backup recovery](https://github.com/kudama/forge/issues/7) | Blocked on operator timing and backup access | Forge |
| [Reject empty final model responses](https://github.com/kudama/forge/issues/8) | Ready | Local implementer, Forge review |
| [Prepare Ubuntu controller deployment](https://github.com/kudama/forge/issues/9) | Blocked on Proxmox stabilization and target details | Forge |

The table records the original seed, not current status. Issue states and the Project board take precedence
as work progresses. No autonomous issue polling or new GitHub permissions for
local workers are installed by this workflow.
