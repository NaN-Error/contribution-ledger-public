/** Navigation guidance only. These steps never acknowledge policies or approve work. */
export type StartPath = 'manual' | 'existing';
export interface GuideStep {
  id: string; title: string; location: string; action: string; expected: string;
  boundary: string; documentation: string; paths: readonly StartPath[];
}
export const guideSteps: readonly GuideStep[] = [
  { id: 'team', title: 'Create your team and project', location: 'Workspaces → Settings and access',
    action: 'Use separate accounts for contributors and an independent reviewer. Start with fictional people and data.',
    expected: 'The intended members can enter this project, and unrelated accounts cannot.',
    boundary: 'Administrator access does not bypass the independent contribution-review rule.',
    documentation: 'docs/account_access.md', paths: ['manual', 'existing'] },
  { id: 'policy', title: 'Review the rules before budgeting work', location: 'Project → Policies',
    action: 'Create and inspect a policy, approve the version, and have each required participant acknowledge it in their own account.',
    expected: 'The approved version is effective and shows no required acknowledgements missing.',
    boundary: 'An example policy is not your agreement, company ownership, or an automatic entitlement.',
    documentation: 'docs/policies_and_budgets.md', paths: ['manual', 'existing'] },
  { id: 'budget', title: 'Approve a milestone budget', location: 'Project → Milestones',
    action: 'For a first fictional exercise, propose 1,000 units and a 100-unit protected reserve. Review and explicitly approve the proposal.',
    expected: 'The approved total, protected reserve and remaining planning capacity are visible; issued units are still zero.',
    boundary: 'Reserve and planned capacity belong to nobody until accepted work issues credit.',
    documentation: 'docs/policies_and_budgets.md', paths: ['manual', 'existing'] },
  { id: 'import', title: 'Connect only authorized repository evidence', location: 'Project → GitHub',
    action: 'Follow the optional GitHub App setup guide, authorize a selected repository, and run a small bounded import.',
    expected: 'Captured source versions and omissions are visible. Map observed identities explicitly.',
    boundary: 'An import does not award units. Keep private source access limited and do not paste keys into chat.',
    documentation: 'docs/github_setup.md', paths: ['existing'] },
  { id: 'history', title: 'Review historical candidates and missing work', location: 'Project → Historical review',
    action: 'Use a dedicated milestone for the historical batch. Correct grouping and attribution, invite missing non-code claims, then promote reviewed candidates through the ordinary package process.',
    expected: 'Each promoted candidate has an approved allocation and an ordinary draft work package.',
    boundary: 'GitHub cannot reconstruct all design, art, production or testing work. Resolve missing claims before archiving an opening balance.',
    documentation: 'docs/reconstruction.md', paths: ['existing'] },
  { id: 'package', title: 'Budget a useful outcome', location: 'Project → Milestones → Work packages',
    action: 'Approve a 100-unit allocation, create a package, and divide it into 60/25/15-unit deliverables. Assign every proposed unit and define measurable acceptance criteria.',
    expected: 'The approved package can move to in progress without increasing its parent budget.',
    boundary: 'Planned allocations are not earned credit. Submission does not mean completion.',
    documentation: 'docs/work_packages.md', paths: ['manual'] },
  { id: 'evidence', title: 'Attach evidence and submit the exact version', location: 'Work package → Evidence',
    action: 'Add a short test report, artifact, design statement or explicitly shared source. Inspect visibility and omissions before submitting.',
    expected: 'The submission preserves the exact scope and evidence snapshot.',
    boundary: 'An author claim is not independent proof. Replacing evidence makes unfinished reviews stale.',
    documentation: 'docs/evidence_and_artifacts.md', paths: ['manual', 'existing'] },
  { id: 'review', title: 'Review independently and finalize accepted work', location: 'Project → Human reviews',
    action: 'Assign a permitted non-beneficiary reviewer. Inspect original evidence, decide each criterion with reasons, and separately finalize accepted deliverables.',
    expected: 'Only accepted deliverables issue units. Repeating finalization does not issue them twice.',
    boundary: 'AI is optional and never completes this decision. A partially accepted package may retain pending deliverables.',
    documentation: 'docs/human_review_and_credit.md', paths: ['manual', 'existing'] },
  { id: 'simulate', title: 'Inspect contribution shares and a hypothetical distribution', location: 'Project → Contribution overview → Revenue simulator',
    action: 'Select the source-credit policy, calculation policy, month and fictional distributable amount. Inspect denominators and rounding before saving an example.',
    expected: 'The result reconciles to the hypothetical total, or clearly identifies a blocked or unallocated pool.',
    boundary: 'Filtering the visible person does not change the denominator. A saved example is not money owed.',
    documentation: 'docs/revenue_simulator.md', paths: ['manual', 'existing'] },
  { id: 'finance', title: 'Practice a synthetic financial close and export', location: 'Project → Financial records',
    action: 'Use fictional receipts and supporting documents, review entries, inspect the close proposal, and download the frozen JSON/CSV after approval.',
    expected: 'Re-exporting does not create another close. The offline replay script reproduces the frozen calculation.',
    boundary: 'This release rejects real-use finance. External payment declarations do not send or independently verify money.',
    documentation: 'docs/finance.md', paths: ['manual', 'existing'] },
];
export function stepsFor(path: StartPath, query = ''): GuideStep[] {
  const term = query.trim().toLocaleLowerCase();
  return guideSteps.filter(step => step.paths.includes(path) &&
    `${step.title} ${step.location} ${step.action}`.toLocaleLowerCase().includes(term));
}
export function phaseStatus(number: number): string {
  if (number === 15) return 'Evaluation tools · human pilot pending';
  if (number === 16) return 'Internal test candidate · verification open';
  return 'Implemented · verification open';
}
