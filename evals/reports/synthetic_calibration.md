# Offline evaluator report

**Synthetic references only. This report does not authorize deployment or compensation.**

Split: calibration. Cases: 126; scenario families: 18.

| Measurement | Result |
|---|---|
| Predictions supplied | 100.0% (126/126) |
| Valid output coverage | 100.0% (126/126) |
| Criterion coverage | 100.0% (378/378) |
| Agreement with allowed synthetic labels | 33.3% (126/378) |
| Invalid output rate | 0.0% (0/126) |
| Generation failure rate | 0.0% (0/126) |
| Supported predictions not allowed by reference | Not measured (zero denominator) |

## Interpretation

The mock provider always answers insufficient. Its stability measures protocol behavior, not useful evidence evaluation.
No human reviewer changes, human pilot observations, or real model-quality measurements are present.

Known cost: 0 micro-USD; 0 rows have unknown cost.
Unknown latency and token usage remain unknown, not zero.

## Controlled perturbations

| Variant | Changed pairs | Unscored pairs |
|---|---|---|
| alias_swap | 0.0% (0/18) | 0 |
| embedded_instruction | 0.0% (0/18) | 0 |
| formatting | 0.0% (0/18) | 0 |
| source_order | 0.0% (0/18) | 0 |
| split_sources | 0.0% (0/18) | 0 |
| verbosity | 0.0% (0/18) | 0 |

## Limits

Developer-authored synthetic references, including deliberately ambiguous examples; not independently reviewed ground truth.

Variants within one family are correlated, not independent experiments; no statistical significance claim.

Citation existence does not establish truth; fabricated or misleading interpretations still require human review.

Imported provider/model/usage fields are operator assertions, not provider-attested records.

No project data, credentials, database, contribution award, financial close or network call is used by this harness.

Mock stability and structural validity do not demonstrate model accuracy or neutrality.


Report fingerprint: `736cc3d0058dedffb4732213a5400f1cc2a293d246c68b170beee9514f7a4117`
