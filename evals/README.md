# Offline evaluator checks

This directory contains **168 explicitly synthetic cases derived from 24 scenario families**. Seven related variants per family are correlated tests, not 168 independently observed projects. The calibration split contains 126 cases from 18 families; the holdout contains 42 cases from six different families.

The annotations are developer-authored expectations. **No independent human reference panel has reviewed them, no actual model-quality benchmark was run, and no human pilot was completed.** A few entries deliberately allow two interpretations. Those are synthetic ambiguity annotations, not invented reports of human disagreement.

## Run without keys or a provider

From the repository root, with the project's Python dependencies installed:

```text
python scripts/evaluate.py mock --output .local/evaluation/my-calibration-run
```

The harness invokes the actual deterministic mock adapter through the existing evidence prompt and output validator. Only the packet goes to generation; expected labels never enter it. The mock always returns insufficient and costs nothing. A report can therefore pass every JSON/reference check while failing the provisional evidence-agreement threshold. That is intentional.

The command writes report.json, report.md and a receipt into a new directory. It never overwrites a previous run. It does not open a database, access credentials, enqueue work, send a network request, issue contribution units or close a financial period. No raw imported model prose is copied into the report. Operator outputs can still reveal sensitive case identifiers; keep actual results under ignored `.local/` and inspect files before sharing.

## Cases and perturbations

The scenarios span code, security, testing, maintenance, infrastructure, art, animation, audio, localization, writing, research, community, marketing, production, paid work and AI-assisted work. Many distinguish a claim from its evidence and the contents of a supplied report from independently verified real behavior. Images and missing external context remain explicit omissions.

Each family includes a baseline, swapped contributor aliases, reordered sources/criteria, neutral verbosity, formatting changes, fragmented source records, and an embedded malicious instruction. IDs and presentation order are varied across families so an evaluator cannot succeed simply by always declaring C1 supported. Variants preserve their family's references.

Alias swaps test packet-local identity sensitivity, not demographic fairness. Fragmenting source records is a controlled proxy for splitting activity, not proof that arbitrary pull-request splitting is harmless. Actual primary-source deduplication and budget limits have separate application tests. This is not a comprehensive adversarial benchmark.

## Holdout procedure

Ordinary calibration does not read holdout case contents. Family IDs and expected file hashes are in the manifest. No family crosses splits. The author who created these fixtures has seen the cases; this is a process separation, not a secret or independently administered benchmark.

Before evaluating the holdout, record and freeze the prompt/profile, reference version, provisional thresholds and evaluation question. An explicit `--split holdout --allow-holdout --reason "..."` is required, and the receipt records why it was opened. The shipped verification only inspected holdout structure with explicit authorization; it did not run predictions or score the holdout. Do not tune to a held-out result and continue calling it unseen.

Changing the corpus or thresholds requires a new version and documented review. The fixture generator refuses an existing output directory. Checksums detect accidental alteration, not forgery by someone who controls the files.

## Score authorized outputs offline

```text
python scripts/evaluate.py score --predictions .local/approved-predictions.jsonl --output .local/evaluation/model-a
```

There is deliberately no live provider runner here. Any collection of live outputs must use the application's approved packet disclosure and payer authorization, or a separately authorized process; this tool grants neither. The offline format is documented in `docs/evaluator_validation.md`.

Packets, prompts and evaluator identities must match. Duplicate cases, unknown cases and mixed requested profiles are rejected. A returned-model change is reported, and prevents passing the provisional stable-model check. Missing outputs, refusals, timeouts, invalid JSON, and fabricated source references remain visible instead of disappearing from the denominator.

Reports separate structural validity, reference-label agreement, support inconsistent with the reference, class-specific confusion, category coverage, declared omissions, paired perturbations, latency, supplied token usage, and known costs. Unknown values stay unknown. There is no objective-worth score, universal fairness score, or benchmark-driven payout.
