import { useRef, useState } from 'react';
import { TextField } from '../../components/shared.js';
import { Feedback, SelectField, Submit, TextArea } from '../../components/forms.js';
import { useAction } from '../../hooks/useApi.js';
import { api } from '../../lib/api.js';
import { boundedEvidenceBody, emptyMetadata, evidenceCategories, prepareFile, safeSourceURL,
  type EvidenceKind, type EvidenceRecord, type EvidenceMetadata, type EvidenceCategory, type Inclusion, type Visibility } from '../../lib/evidence.js';
import type { WorkPackageDetail } from '../../lib/workPackages.js';
import { humanLabel } from '../../lib/planning.js';

export function EvidenceEditor({ root, packageRecord, initial, saved, cancel }: {
  root: string; packageRecord: WorkPackageDetail; initial?: EvidenceRecord; saved: () => void; cancel: () => void;
}) {
  const [kind, setKind] = useState<EvidenceKind>(initial?.kind || 'statement');
  const [metadata, setMetadata] = useState<EvidenceMetadata>(initial ? { ...initial.document.metadata, deliverable_ids: [...initial.document.metadata.deliverable_ids] } : emptyMetadata());
  const [text, setText] = useState(initial?.document.text || '');
  const [url, setURL] = useState(initial?.document.source_url || '');
  const [file, setFile] = useState<File | null>(null); const [reason, setReason] = useState(''); const action = useAction();
  const attempt = useRef<{ body: string; id: string } | null>(null);
  function update<K extends keyof EvidenceMetadata>(key: K, value: EvidenceMetadata[K]) { setMetadata(current => ({ ...current, [key]: value })); }
  return <section className="panel evidence-editor"><div className="section-heading"><h3>{initial ? `New revision of ${initial.document.metadata.title}` : 'Add contribution evidence'}</h3><button className="button" onClick={cancel} disabled={action.pending}>Cancel</button></div>
    <p className="muted">Describe the source and its relevance. Claimed authorship is not automatically verified. Nothing here awards units.</p>
    <Feedback error={action.error} /><form onSubmit={event => { event.preventDefault(); void action.run(async () => {
      const source_url = kind === 'link' ? safeSourceURL(url.trim()) : null;
      const upload = kind === 'file' && file ? await prepareFile(file) : null;
      if (kind === 'file' && !initial && !upload) throw new Error('Select the artifact to upload.');
      const meta = { ...metadata, inclusion: kind === 'unavailable' ? 'unavailable' : metadata.inclusion,
        omission_reason: kind !== 'unavailable' && metadata.inclusion === 'included' ? null : metadata.omission_reason };
      const payload = { metadata: meta, text: kind === 'statement' ? text : null, source_url, file: upload,
        expected_package_version: packageRecord.version, reason,
        ...(initial ? { expected_revision: initial.number } : { kind }) };
      const serialized = JSON.stringify(payload);
      if (attempt.current?.body !== serialized) attempt.current = { body: serialized, id: crypto.randomUUID() };
      return api(initial ? `${root}/${initial.evidence_id}/revisions` : root, 'POST',
        boundedEvidenceBody({ ...payload, request_id: attempt.current!.id }));
    }, saved); }}>
      <fieldset disabled={action.pending} className="evidence-fieldset"><SelectField label="Evidence type" value={kind} disabled={!!initial || action.pending} onChange={e => {
        const value=e.target.value as EvidenceKind;setKind(value);update('inclusion',value==='unavailable'?'unavailable':'included');
      }}><option value="statement">Contributor statement or review note</option><option value="link">External source link</option><option value="file">Upload a text or image artifact</option><option value="unavailable">Missing evidence / limitation</option></SelectField>
      <div className="form-grid"><TextField label="Evidence title" required minLength={2} maxLength={120} value={metadata.title} onChange={e => update('title',e.target.value)} />
      <SelectField label="Evidence category" value={metadata.category} onChange={e=>update('category',e.target.value as EvidenceCategory)}>{evidenceCategories.map(c=><option key={c} value={c}>{humanLabel(c)}</option>)}</SelectField></div>
      <TextArea label="Relevance to the work" required minLength={3} maxLength={1000} rows={3} value={metadata.description} onChange={e=>update('description',e.target.value)} />
      <TextField label="Claimed author or authors" required minLength={3} maxLength={1000} value={metadata.claimed_authors} onChange={e=>update('claimed_authors',e.target.value)} hint="Name the people who created the source, not simply the person uploading it." />
      <TextArea label="Source and provenance" required minLength={3} maxLength={1000} rows={2} value={metadata.provenance} onChange={e=>update('provenance',e.target.value)} />
      <TextField label="Claimed date of the work" type="date" required value={metadata.occurred_on} onChange={e=>update('occurred_on',e.target.value)} />
      <SelectField label="Who can inspect this evidence?" value={metadata.visibility} onChange={e=>update('visibility',e.target.value as Visibility)}>
        <option value="project">People with current project access</option><option value="restricted">Submitter, project reviewers and administrators only</option></SelectField>
      <p className="small muted">Restriction applies to earlier versions too. Earlier restricted versions remain restricted if a new revision is made project-visible. Already saved copies cannot be recalled.</p>
      <SelectField label="Include this evidence in review?" value={metadata.inclusion} disabled={kind==='unavailable'} onChange={e=>update('inclusion',e.target.value as Inclusion)}>
        <option value="included">Included for human review</option><option value="excluded">Excluded, with an explanation</option><option value="unavailable">Unavailable / incomplete source</option></SelectField>
      {metadata.inclusion!=='included' && <TextArea label="Reason for exclusion or unavailability" required minLength={3} maxLength={1000} value={metadata.omission_reason || ''} onChange={e=>update('omission_reason',e.target.value)} />}
      {kind==='statement' && <TextArea label="Contributor statement" required maxLength={12000} rows={7} value={text} onChange={e=>setText(e.target.value)} />}
      {kind==='link' && <><TextField label="HTTPS source URL" type="url" required maxLength={2000} value={url} onChange={e=>setURL(e.target.value)} /><p className="small muted">Only the URL is saved. The application does not fetch or verify the page, and the source may change independently.</p></>}
      {kind==='file' && <div className="artifact-drop"><TextField label={initial?'Replacement artifact (optional)':'Artifact file'} type="file" required={!initial} accept=".txt,.md,.csv,.json,.png,.jpg,.jpeg,.webp" onChange={e=>setFile(e.target.files?.[0] || null)} />
        <p>Static PNG, JPEG or WebP: up to 2 MiB. UTF-8 TXT, MD, CSV or JSON: up to 256 KiB. Raster images are limited to 8 million pixels.</p>
        {initial && <p>Leaving the file empty keeps the existing bytes and creates a metadata revision. Choose a replacement to preserve the old artifact and upload a new version.</p>}
        <p className="small muted">No archives, scripts, executables or game projects. Original files are not malware-scanned and may contain metadata. Preview images are regenerated without that metadata.</p></div>}
      <fieldset className="evidence-deliverables"><legend>Related deliverables (optional)</legend><p className="small">Leave unselected when this evidence relates to the whole package.</p>
        {packageRecord.revision.document.deliverables.map(d=><label key={d.id}><input type="checkbox" checked={metadata.deliverable_ids.includes(d.id)} onChange={e=>update('deliverable_ids',e.target.checked?[...metadata.deliverable_ids,d.id]:metadata.deliverable_ids.filter(id=>id!==d.id))} />{d.title}</label>)}
        {metadata.deliverable_ids.some(id=>!packageRecord.revision.document.deliverables.some(d=>d.id===id)) && <button type="button" className="button" onClick={()=>update('deliverable_ids',metadata.deliverable_ids.filter(id=>packageRecord.revision.document.deliverables.some(d=>d.id===id)))}>Remove references to superseded deliverables</button>}
      </fieldset>
      <TextArea label="Reason for this evidence entry or revision" required minLength={8} maxLength={500} rows={2} value={reason} onChange={e=>setReason(e.target.value)} />
      <Submit pending={action.pending}>{initial?'Save new evidence revision':'Save evidence and capture snapshot'}</Submit></fieldset></form>
  </section>;
}
