# Deferred two-period shadow pilot

**Status: not started. No people, periods or review observations have been invented.** The empty observations template is intentional.

This human stage does not block installation or fictional local testing. It does block claiming a completed real-team pilot or meaningful real-world evaluator validation. Existing compensation arrangements must remain unchanged during the pilot.

Before beginning, make the deployment pass its build, browser, native database, permissions and restore checks. Confirm participant agreement to the work and any provider disclosure. Use actual independent reviewers; multiple accounts controlled by one tester are acceptable for software tests but do not establish human independence.

Run at least two complete, non-overlapping review periods. Preserve work-package and evidence references, each manual finding, each permitted AI-assisted finding, subsequent human changes, disputes, missing non-code work, observed review time and attempts to reconstruct a distribution. Do not turn unknown durations or outcomes into zeros. Counterbalance review order where practical and acknowledge that repeated exposure and familiarity can influence timing.

Store actual records outside this source tree, under a protected location such as `.local/pilot/`. Use pseudonymous participant labels. The report exporter does not magically anonymize detailed notes, and the source ZIP must never include real observations.

`python scripts/pilot_summary.py docs/pilot/observations_template.json` reports zero observations and unknown outcomes. Once real authorized observations exist, use a separate local JSON file with the documented schema. The command is a descriptive summarizer only; even two populated periods leave `human_pilot_verified` and `deployment_authorized` false.

## Observation format

The top-level object contains `schema_version: shadow-observations-v1`, `periods` and `observations`. Each period needs a unique `id`, timezone-aware ISO `start` and `end`, `compensation_unchanged: true`, and a supporting `record_reference`. Periods cannot overlap.

Each observation needs `period_id`, a pseudonymous `participant_alias`, `work_reference`, `manual_seconds`, `assisted_seconds`, `changed_ai_finding`, `reconstructed_distribution`, and `record_reference`. Durations are integers or null. Outcomes are true/false or null. Do not provide the same participant/work/period pair twice. Different interpretations belong in the actual review records, not duplicate rows counted as more people.

The summary reports known versus unknown paired durations, human-changed findings and reconstruction results. A positive manual-minus-assisted duration is descriptive, not proof that AI caused a time saving. Aliases, record authenticity, case selection and completeness require independent review outside this program.

No function in this tool changes accounts, contribution units, readiness flags, provider settings or financial records.
