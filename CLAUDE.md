# Teleprompt – Claude Code Guidelines

## Workflow

1. **Plan first** — always enter planning mode before any implementation. Present the plan and wait for approval before writing code.

2. **Branch** — after plan approval, fetch and pull the latest `main` from remote, then create a new feature branch:
   ```
   git fetch origin && git checkout main && git pull origin main
   git checkout -b feature/<short-description>
   ```

3. **Tests before implementation** — write test cases first based on the feature or fix:
   - Backend changes → pytest tests in `backend/tests/`
   - Frontend changes → Vitest tests in `frontend/tests/`
   - If the change touches both → break the task into backend and frontend parts and write tests for each

4. **Implement until tests pass** — write the implementation and iterate until all new (and existing) tests are green.

5. **Commit** — use conventional commits:
   - `feat:` new feature
   - `fix:` bug fix
   - `test:` adding or updating tests
   - `ci:` CI/CD changes
   - `chore:` maintenance

6. **Push and open a PR** — push the branch and create a GitHub PR with a clear summary and test plan.

## Backlog

Any feature or improvement that is out of scope for the current task must be captured as a GitHub issue before moving on. Do not add TODO comments in code — open an issue instead.

## Permissions

- Planning mode approval is required before implementation begins.
- No further permission is needed after plan approval — proceed through steps 2–6 autonomously.
- If the plan changes mid-implementation, stop and ask for approval on the revised plan before continuing.
