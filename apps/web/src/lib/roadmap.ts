export const phases = [
  ['Project foundation', 'Local browser, API, database, migration and test baseline.'],
  ['Accounts and project access', 'Accounts, invitations, workspace isolation and roles.'],
  ['Policies and milestone budgets', 'Versioned rules, approved budgets and unissued reserves.'],
  ['Work packages', 'Useful outcomes, acceptance criteria and contributor proposals.'],
  ['Evidence and non-code work', 'Artifacts, provenance and immutable review snapshots.'],
  ['Review and contribution ledger', 'Human decisions, exact credit, disputes and corrections.'],
  ['Revenue simulator', 'Explainable hypothetical distributions; no payments.'],
  ['GitHub historical import', 'Selected repository evidence and contributor identity review.'],
  ['Reliable synchronization', 'Webhooks, durable jobs, retries and reconciliation.'],
  ['AI connections and model catalog', 'Permitted provider connections and approved evaluator profiles.'],
  ['AI-assisted evidence review', 'Evidence-grounded suggestions with human approval.'],
  ['Project reconstruction', 'Reviewable historical opening balances and contribution explanations.'],
  ['Distribution records', 'Financial periods, frozen calculations and exports.'],
  ['Security and recovery', 'Hardening, tested restoration and restricted deployment.'],
  ['Evaluation and shadow pilot', 'Measured review quality and a human pilot without changed pay.'],
  ['Limited invited release', 'Onboarding, release documentation and an explicit go-live decision.'],
] as const;

export function filterPhases(query: string) {
  const value = query.trim().toLocaleLowerCase();
  return phases.map(([title, description], index) => ({ number: index + 1, title, description }))
    .filter(phase => `${phase.number} ${phase.title} ${phase.description}`.toLocaleLowerCase().includes(value));
}
