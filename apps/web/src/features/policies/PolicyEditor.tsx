import { useState } from 'react';
import { TextField } from '../../components/shared.js';
import { Feedback, SelectField, Submit, TextArea } from '../../components/forms.js';
import { useAction } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import type { Project } from '../../lib/accounts.js';
import { categories, deductions, formatBps, humanLabel, parseWeight, type Policy, type PolicyRules, type PolicyTemplate } from '../../lib/planning.js';

export function PolicyEditor({ project, source, template, latestVersion, onSaved, onCancel }: {
  project: Project; source: Policy | null; template: PolicyTemplate; latestVersion: number; onSaved: (item: Policy) => void; onCancel: () => void;
}) {
  const [rules, setRules] = useState<PolicyRules>(() => ({ ...structuredClone(source?.rules || template.rules), timezone: project.timezone }));
  const [title, setTitle] = useState(source?.title || 'Contribution policy');
  const [reference, setReference] = useState(source?.agreement_reference || '');
  const [reason, setReason] = useState('');
  const [mixed, setMixed] = useState(rules.pools.length === 2);
  const [release, setRelease] = useState(formatBps((rules.pools.find(pool => pool.key === 'release')?.weight_bps ?? 10000)).replace('%', ''));
  const action = useAction();
  const accounting = <K extends keyof PolicyRules['accounting']>(key: K, value: PolicyRules['accounting'][K]) => setRules(old => ({ ...old, accounting: { ...old.accounting, [key]: value } }));
  const root = `/api/v1/workspaces/${project.workspace_id}/projects/${project.id}/policies`;
  return <section className="panel policy-editor"><div className="section-heading"><h2>{source ? `Create version ${latestVersion + 1}` : 'Create the first policy draft'}</h2><button className="button" onClick={onCancel}>Cancel draft</button></div>
    <p className="planning-warning">{source ? 'Saving creates a new immutable revision. Existing approvals and acknowledgements will not carry over.' : 'This is an example, not an accepted agreement. Review and replace example terms before approval.'} No credit or ownership is created here.</p>
    <Feedback error={action.error} />
    <form onSubmit={event => { event.preventDefault(); void action.run(async () => {
      const releaseBps = mixed ? parseWeight(release) : 10000;
      if (releaseBps <= 0 || (mixed && releaseBps >= 10000)) throw new Error('A two-pool policy requires each pool to have a positive share.');
      const pools: PolicyRules['pools'] = [{ key: 'release', weight_bps: releaseBps, eligibility: 'accepted_release_work' }];
      if (mixed) pools.push({ key: 'ongoing', weight_bps: 10000 - releaseBps, eligibility: 'accepted_work_in_accounting_period' });
      return api<Policy>(root, 'POST', { expected_latest_version: latestVersion, title,
        agreement_reference: reference, reason, rules: { ...rules, pools } });
    }, onSaved); }}>
      <div className="form-grid"><TextField label="Policy title" required minLength={2} maxLength={120} value={title} onChange={e => setTitle(e.target.value)} />
      <TextField label="Agreement reference" required minLength={8} maxLength={500} value={reference} onChange={e => setReference(e.target.value)} hint="A document reference, or an explicit synthetic-only test reference. The app does not fetch or verify it." /></div>
      <div className="form-grid"><TextField label="Policy accounting timezone" value={rules.timezone} readOnly hint="Copied from current project settings. This version preserves its own timezone." /><TextField label="Policy currency" value={rules.currency} readOnly hint="USD only. Financial calculations are a later phase." /></div>
      <fieldset className="choice-group"><legend>Eligible contribution categories</legend><p>Non-code work uses the same outcome-based rules.</p><div className="checkbox-grid">{categories.map(category => <label key={category}><input type="checkbox" checked={rules.eligible_categories.includes(category)} onChange={e => setRules(old => ({ ...old, eligible_categories: e.target.checked ? [...old.eligible_categories, category] : old.eligible_categories.filter(c => c !== category) }))} />{humanLabel(category)}</label>)}</div></fieldset>
      <h3>Contribution and review rules</h3>
      <SelectField label="Independent reviewers required for future credit acceptance" value={rules.review.minimum_independent_reviewers} onChange={e => setRules(old => ({ ...old, review: { ...old.review, minimum_independent_reviewers: Number(e.target.value) } }))}>{[1, 2, 3].map(n => <option key={n} value={n}>{n}</option>)}</SelectField>
      <p>A beneficiary cannot be the sole independent approver. These are configured rules for the later acceptance workflow; phase 3 cannot issue contribution units.</p>
      <TextArea label="Attribution rule" required minLength={12} maxLength={2000} rows={3} value={rules.attribution_rule} onChange={e => setRules(old => ({ ...old, attribution_rule: e.target.value }))} />
      <TextArea label="Departure and historical-credit rule" required minLength={12} maxLength={2000} rows={3} value={rules.departure_rule} onChange={e => setRules(old => ({ ...old, departure_rule: e.target.value }))} />
      <h3>Revenue-pool policy</h3>
      <SelectField label="Pool structure" value={mixed ? 'mixed' : 'release'} onChange={e => { setMixed(e.target.value === 'mixed'); if (e.target.value === 'mixed' && release === '100.00') setRelease('70.00'); }}><option value="release">Release pool only</option><option value="mixed">Release and ongoing pools</option></SelectField>
      {mixed && <TextField label="Release pool share (%)" required inputMode="decimal" value={release} onChange={e => setRelease(e.target.value)} hint="Up to two decimal places. The ongoing pool receives the remainder to 100%. This is a pool weight, not a contributor's percentage." />}
      <p>Release: accepted release work. Ongoing: accepted work in the accounting period. Unissued units remain unowned; unresolved attribution or an empty pool blocks a close.</p>
      <h3>Accounting and deductions</h3>
      <p>Calendar months begin on day 1 at 00:00 in the policy timezone. Ambiguous or nonexistent local boundaries must be rejected rather than guessed when the accounting workflow is added.</p>
      <SelectField label="Revenue basis" value={rules.accounting.revenue_basis} onChange={e => {
        const basis = e.target.value as PolicyRules['accounting']['revenue_basis'];
        setRules(old => ({ ...old, accounting: { ...old.accounting, revenue_basis: basis,
          allowed_deductions: basis === 'net_storefront_settlements' ? old.accounting.allowed_deductions.filter(x => x !== 'platform_fees') : old.accounting.allowed_deductions } }));
      }}><option value="net_storefront_settlements">Net storefront settlements</option><option value="gross_receipts">Gross receipts</option></SelectField>
      <fieldset className="choice-group"><legend>Permitted deduction categories</legend><div className="checkbox-grid">{deductions.map(item => <label key={item}><input type="checkbox" checked={rules.accounting.allowed_deductions.includes(item)} disabled={item === 'platform_fees' && rules.accounting.revenue_basis === 'net_storefront_settlements'} onChange={e => accounting('allowed_deductions', e.target.checked ? [...rules.accounting.allowed_deductions, item] : rules.accounting.allowed_deductions.filter(x => x !== item))} />{humanLabel(item)}</label>)}</div><p>Platform fees cannot be deducted again from net storefront settlements. Other categories require evidence that the same amount has not already been deducted.</p></fieldset>
      <TextArea label="Definition of distributable earnings" required minLength={12} maxLength={2000} rows={3} value={rules.accounting.distributable_definition} onChange={e => accounting('distributable_definition', e.target.value)} />
      <TextArea label="Cash-reserve rule" required minLength={12} maxLength={2000} rows={3} value={rules.accounting.reserve_rule} onChange={e => accounting('reserve_rule', e.target.value)} />
      <TextArea label="Capital-repayment rule" required minLength={12} maxLength={2000} rows={3} value={rules.accounting.capital_repayment_rule} onChange={e => accounting('capital_repayment_rule', e.target.value)} />
      <h3>Approval requirements in this release</h3><p>A project administrator approves policy versions and budget changes. Every required participant reviews and acknowledges the exact policy. Administrators may approve their own planning proposals; this does not satisfy independent review for future contribution awards.</p>
      <p>Actual agreement signing, ownership, worker classification, and legal review take place outside this application.</p>
      <TextField label="Reason for this policy revision" required minLength={8} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} />
      <Submit pending={action.pending}>Save new policy revision</Submit>
    </form>
  </section>;
}
