# Evaluator validation and offline results

Version 0.16.0-phase16. This adds the self-contained P15A/P15B tools while leaving live quality evaluation and the real P15C shadow pilot open.

## Reference quality comes first

The supplied 24 scenario families (168 controlled variants) are synthetic author expectations. They demonstrate wiring, labels, omission handling and failure visibility. They are not independently reviewed gold data. Before drawing model-quality conclusions, obtain authorized representative cases and independent references; preserve dissent and ambiguous interpretation. Keep the holdout family-disjoint and freeze its evaluation criteria before scoring it. Do not infer fairness from one aggregate number.

The provisional thresholds are 90% agreement with allowed synthetic labels, no reference-contradicting support, complete valid coverage, a stable single returned model, and no more than 5% changed pairs per perturbation. These are development alerts, not validated business requirements or release authorization. Passing them never sets application readiness or economic rights. The synthetic mock is always disqualified as a quality result.

## Strict prediction interchange

Use one JSON object per case per line. Unknown extra fields are rejected. Each object contains:

| Field | Meaning |
|---|---|
| case_id | Exact corpus case ID |
| packet_fingerprint | SHA-256 of canonical packet JSON |
| prompt_fingerprint | Existing application's prompt_hash(packet), including prompt/schema/instructions |
| provider, requested_model | One stable requested evaluator identity for the entire report |
| returned_model | Recorded returned model identifier, or null if unavailable |
| profile_fingerprint | 64-character lowercase hex fingerprint of the frozen evaluation profile |
| origin | offline_operator_supplied, or synthetic_mock only for the no-network fixture |
| finish | complete, timeout, refused, truncated, model_unavailable, or failure |
| content | The exact model JSON as a string, or null for absent output; at most 65,536 UTF-8 bytes |
| latency_ms | Nonnegative integer, or null |
| cost_micro_usd | Exact nonnegative integer represented as a decimal string, or null |
| input_tokens, output_tokens | Nonnegative integers, or null |

The existing evidence-assessment-v1 validator checks the output. It rejects extra authority fields, missing/duplicate criteria, invented contributor aliases, and invalid citations. Citation existence does not establish that the interpretation is true. An apparently plausible but unsupported explanation still needs human review.

The envelope contains operator assertions, not a provider signature. An operator can fabricate results; hashes cannot make those assertions independently trustworthy. Do not paste raw private output, model keys, or participant data into a public repository.

## Metrics and denominators

Coverage includes every selected corpus case, including missing, failed and invalid outputs. Reference agreement is computed only where a valid finding exists, with its separate criterion coverage shown beside it. Whole-case agreement retains the full case denominator. Multi-interpretation criteria are counted as ambiguous and excluded from the single-label confusion matrix.

The “supported predictions not allowed by reference” metric is a comparison with the supplied synthetic annotations, not an automatic fact-check of all claims in the explanation. Per-class precision/recall and category counts remain separate. Reports do not compress them into personal contribution percentages.

Sensitivity compares each valid variant with the valid baseline of the same family. Missing or invalid pairs are unscored, not stable. Correlated variants do not justify a statistical significance claim. There is no causal inference from a difference in these descriptive results.

Latency, usage and costs are imported measurements. The mock's byte-count approximation is deliberately not reported as real token usage. Unknown values remain null/unknown and the cost total includes only known rows. Never interpret that total as the provider's complete bill.

## Failure and security coverage

The new offline tests exercise missing rows, malformed envelopes, duplicate cases, invalid citations, extra authority fields, altered files, threshold changes, model substitutions, retired models, refusals, truncations, and unknown cost. Existing application tests continue to exercise disclosure permissions, payer approval, uncertain billing, stale evidence, revocation, tenant isolation and exact-budget reservations. Native concurrency and live provider failures still require their separately tracked checks.

The evaluator harness imports no runtime database session and has no network runner. A repository instruction cannot invoke a ledger command through it. The packet's untrusted instruction is data; the model output is checked with the production assessment validator. A successful mock run does not prove that a real model resists the same attack.

## Reproduce the shipped report

Run `python scripts/evaluate.py mock --output .local/evaluation/reproduction` from the repository root. The input/packet/profile/report fingerprints allow deterministic comparison. The command needs installed project Python packages but no `.env`, Docker service, GitHub App or AI key.

Use `--require-provisional-pass` only when an automation should fail on unmet development thresholds. The mock exits 3 under that option by design. Normal mock completion returns zero to report successful harness execution, not model quality.
