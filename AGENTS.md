# Working on Trading Desk

## Scope

Agree one small slice, implement and verify it, then let the owner review. Do not turn
course examples into extra requirements. Do not commit or push unless asked.

README.md is the only project documentation. Keep the editable diagram in assets/database.svg
consistent with the ORM. Update the README when behavior or setup changes. Do not create phase
reports, roadmaps, workshop plans or collections of scenario files. This file contains agent
instructions, not a second project guide.

## Code

- Keep current service boundaries until a concrete change justifies altering them.
- Numerical pricing stays pure: no database, HTTP, service imports or implicit clock reads.
- Keep handlers focused on HTTP, repositories on persistence and operations on orchestration.
- Give each domain rule and supported capability one owner. Remove replaced code and obsolete
  compatibility paths in the same slice.
- Use an ABC when distinct current implementations need shared behavior. Data records can be
  dataclasses; simple operations can remain functions. Avoid generic repositories, automatic
  registration and dependency-injection frameworks.
- Keep related behavior together. Split a file by responsibility, not to meet a line-count target.
- Database transactions have one clear owner. Helpers participating in an operation do not
  commit independently. Convert ORM data inside the session; do not leak ORM objects outside it.
- Use four-space Python indentation and two-space JavaScript indentation. Follow existing names
  and import conventions. Comments should explain a real constraint, without narrating obvious code.
- Read environment variables through desk_runtime.config. Pin external dependencies in
  requirements.txt and declare package dependencies in the relevant pyproject.toml.
- Keep UI copy about market state and available actions. Do not add implementation explanations
  or purpose captions to panels. Financial calculations and lifecycle rules belong in the backend.

## Verification

Use a disposable development database for schema changes; legacy-data preservation is outside
the agreed scope. Do not delete unrelated data or environments.

Run the changed flow through the services and browser. Check invalid/missing/stale inputs,
closed state, restart and relevant concurrent writes. Recompute financial outputs independently.
Check UI fields using their displayed units and inspect normal/narrow layouts. Run Python
compilation and applicable frontend build/lint/dead-code checks. Keep imports from the old
app/shared package layout absent. Report what passed and what could not be exercised.

Do not add documentation or test scaffolding merely to demonstrate a pattern. Add a focused
repeatable check only when it protects meaningful behavior that is otherwise difficult to verify.
