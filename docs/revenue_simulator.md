# Revenue simulator

Source 0.7.0-phase7. Hypothetical examples only; nothing becomes owed, paid, frozen or vested. No GitHub, AI key, storefront connection or banking account is needed.

## Open the simulator

Sign in, open your workspace, open the project, then choose **Revenue simulator**. The app requires current project access. The earlier Policies, Milestones, Work packages, Evidence and Human reviews workflows produce the finalized credit used here. A submitted package or a positive review by itself is not credit.

Choose the **Source-credit policy** that owns the accepted awards. All matching milestones are considered; other policy versions are excluded and reported. Choose the **Calculation policy** for this example. It can be the same version or a draft alternative. Only that version's pool keys, weights and timezone are used; existing credit and approvals remain under their source policy.

Enter **Hypothetical distributable USD**, such as `10000.00`, without commas or a currency symbol. It means an assumed amount after whatever deductions would be defined elsewhere. This module does not import earnings, calculate profit or deduct expenses. Use **Accounting month** to select a local calendar month under the calculation policy timezone, then select **Calculate hypothetical distribution**.

An empty project produces a clearly blocked pool, not a guessed allocation. A draft with no finalized credit cannot manufacture contributor percentages.

## What the scope means

Release credit is cumulative through the selected month's exclusive end, limited to work already accepted when the preview is captured. Ongoing credit uses the month in which the original award was accepted, not the date its task was created, its files were uploaded or a later correction was made. Start is inclusive; end is exclusive. The exact UTC boundaries are displayed alongside the policy timezone.

Current corrected attribution is used for a fresh preview, including when the selected month is in the past. It is not a historical amount owed or an estimate of what people knew then. A current/future month can be incomplete; no future work is predicted. Release percentages in this screen are not permanently frozen.

Only recognized units in the named source policy, pool and date scope enter its denominator. Accepted non-code work is treated the same as programming. Leaving the project does not erase finalized credit. Unfinished work, unissued reserves and budget proposals appear separately; they do not enter anyone's recognized share. Current planning totals are not month-filtered.

## Read the result

The result shows the assumed amount, calculated recipient amounts, explicitly unallocated cents, pool weights and each pool's exact recognized-unit denominator. Per-person amounts are summed across the enabled pools. Pool details show the whole-cent floor and any rounding cent. Remainders are compared exactly; ties use stable contributor identifiers, never their names or table order.

The same inputs always reproduce the same result. The convention allocates every available cent without floating-point rounding, but a one-cent change can change which person receives a leftover cent. Increasing a total is not guaranteed to increase every individual amount under this method.

A pool with no eligible units is blocked, even for a zero input. An unresolved dispute affecting an included award blocks its pool. Its hypothetical money remains **unallocated**. It does not go to the owner or move to another pool. Unaffected pools may display a partial calculation, but the example remains blocked as a whole. Resolve the concern through the existing independent dispute process and calculate a new example; this screen never resolves it.

## Save and revisit an example

Review the result and warnings. Enter a title, confirm that it is hypothetical and creates no amount owed, and choose **Save hypothetical example**. Saving is optional; the preview action itself creates no saved scenario, award, event or financial obligation. Session activity may still be refreshed by the normal authentication layer.

A save rechecks the current source state. Changed credit, disputes, policy readiness or planning can make the reviewed preview stale. Recalculate, read the changed result, and explicitly save again. There is no hidden retry that saves unreviewed state. Repeating the same successful command does not create a duplicate example.

Saved examples retain their original input, policy/ledger fingerprints, current-at-capture attribution, planning/exclusions, engine version and output. Opening one verifies its fingerprints and reproduces the calculation using the preserved inputs. New awards or a later dispute resolution do not change it. The date displayed is the capture date, not the present ledger state.

**Open project-protected link** provides a local hash link. The recipient must sign in and still have access to this exact project; the identifier is not a sharing credential. Localhost links do not make the app reachable from someone else's computer. All project roles can read/calculate; viewers cannot save. There is no public share, editing of a saved example or automatic expiration/deletion feature.

## Fictional five-person example

The regression test uses 70% release / 30% ongoing, $10,000 and these recognized-unit shares:

| Contributor | Release share | Ongoing share | Hypothetical amount |
|---|---:|---:|---:|
| Alice | 35% | 10% | $2,750.00 |
| Bob | 25% | 20% | $2,350.00 |
| Carla | 20% | 20% | $2,000.00 |
| Diego | 15% | 20% | $1,650.00 |
| Erin | 5% | 30% | $1,250.00 |
| Total | 100% | 100% | $10,000.00 |

Those are fixtures, not mandated economics and not account records seeded into your project. The application-command test creates approved fictional art and research packages, attaches evidence, collects independent acceptance, finalizes their credit, then calculates this result without directly injecting awards. Test accounts do not establish genuine real-world independence.

## Limits and exclusions

The initial currency is USD. The amount limit is $10,000,000,000.00 and inputs accept at most two decimal places. Only one source policy is used per example. There are explicit small-team query limits; exceeding one returns an error rather than omitting work. Projects can retain up to 1,000 examples. Empty and zero-value inputs are not silently normalized into a valid pool.

Actual receipts, permitted expenses, approved accounting periods, final distribution freezes, exports intended for external payment and payment records belong to phase 13. Source-code imports and model evaluations belong to later phases. None are implied by a successful simulation.
