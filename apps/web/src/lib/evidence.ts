import type { ScopeDocument } from './workPackages.js';

export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
export const MAX_TEXT_BYTES = 256 * 1024;
export const MAX_EVIDENCE_JSON_BYTES = 4 * Math.ceil(MAX_UPLOAD_BYTES / 3) + 65536;
export const evidenceKinds = ['statement', 'link', 'file', 'unavailable'] as const;
export type EvidenceKind = typeof evidenceKinds[number];
export const evidenceCategories = ['code', 'art', 'design', 'qa', 'research', 'documentation', 'maintenance', 'marketing', 'other'] as const;
export type EvidenceCategory = typeof evidenceCategories[number];
export type Inclusion = 'included' | 'excluded' | 'unavailable';
export type Visibility = 'project' | 'restricted';
export interface EvidenceMetadata {
  title: string; description: string; claimed_authors: string; provenance: string; occurred_on: string;
  category: EvidenceCategory; visibility: Visibility; inclusion: Inclusion; omission_reason: string | null; deliverable_ids: string[];
}
export interface UploadedFile { filename: string; media_type: string; content_base64: string }
export interface ArtifactInfo {
  filename: string; media_type: string; size_bytes: number; sha256: string;
  width: number | null; height: number | null; preview_sha256: string | null; preview_size_bytes: number | null;
  processing: string; scanner: string;
}
export interface EvidenceDocument {
  schema_version: number; kind: EvidenceKind; metadata: EvidenceMetadata;
  text: string | null; source_url: string | null; file: ArtifactInfo | null;
  external_source?: { provider?:string; source_id?:string; source_hash?:string; kind?:string; remote_key?:string; [key:string]:unknown };
}
export interface EvidenceRecord {
  evidence_id: string; number: number; current_revision: number; kind: EvidenceKind;
  document: EvidenceDocument; content_hash: string; created_by: string; created_at: string; reason: string;
  availability: string; preview_availability: string; can_edit: boolean; historical: boolean; claims_notice: string;
}
export interface EvidenceCollection {
  package_id: string; package_version: number; items: EvidenceRecord[]; total_entries: number; restricted_entries: number;
  offset: number; next_offset: number | null; can_add: boolean; can_snapshot: boolean; can_retire: boolean;
  current_snapshot_id: string | null; current_content_hash: string; last_submission_id: string | null;
  submitted_snapshot_hash: string | null; review_state: 'not_submitted' | 'legacy_without_evidence' | 'current' | 'stale';
  retention_notice: string; limits: { max_upload_bytes: number; max_text_bytes: number; allowed_extensions: string[]; max_entries: number };
}
export interface SnapshotEntry {
  restricted?: false; evidence_id: string; revision: number; revision_hash: string; document: EvidenceDocument;
  availability_at_capture: string; preview_availability_at_capture: string; submitted_by: string;
}
export interface SnapshotSummary { id: string; scope_revision: number; content_hash: string; created_at: string; created_by: string }
export interface EvidenceSnapshot extends SnapshotSummary {
  stale: boolean; redacted: boolean; reason: string; current_content_hash: string; historical_notice: string;
  current_artifact_states?: Record<string, string>;
  document: { scope: ScopeDocument; entries: (SnapshotEntry | { restricted: true })[];
    omissions: { evidence_id: string | null; status: string; reason: string }[]; notice: string; scope_hash: string; policy_hash: string };
}
export const mediaTypes: Readonly<Record<string, string>> = {
  txt: 'text/plain', md: 'text/markdown', csv: 'text/csv', json: 'application/json',
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp',
};
export function localDate(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
export function emptyMetadata(): EvidenceMetadata {
  return { title: '', description: '', claimed_authors: '', provenance: '', occurred_on: localDate(), category: 'other',
    visibility: 'project', inclusion: 'included', omission_reason: null, deliverable_ids: [] };
}
export function formatBytes(size: number): string {
  if (!Number.isSafeInteger(size) || size < 0) throw new Error('Invalid byte count.');
  if (size < 1024) return `${size} bytes`;
  return size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KiB` : `${(size / 1024 / 1024).toFixed(2)} MiB`;
}
export function fileMediaType(filename: string): string {
  if (filename.length > 120 || /^[.\- ]/.test(filename) || /[. ]$/.test(filename) || filename.includes('..')
      || /[\/\\:%<>|?*"\p{Cc}\p{Cf}]/u.test(filename)) throw new Error('Use a short filename without paths, reserved symbols or hidden controls.');
  if (/^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)/i.test(filename)) throw new Error('This filename is reserved. Rename the file.');
  const extension = filename.split('.').pop()?.toLowerCase() || '';
  const type = mediaTypes[extension];
  if (!type) throw new Error('Allowed files: TXT, MD, CSV, JSON, PNG, JPEG and static WebP.');
  return type;
}
export function encodeFile(filename: string, data: Uint8Array): UploadedFile {
  const media_type = fileMediaType(filename);
  const limit = media_type.startsWith('image/') ? MAX_UPLOAD_BYTES : MAX_TEXT_BYTES;
  if (!data.length || data.length > limit) throw new Error(`This file must contain between 1 byte and ${formatBytes(limit)}.`);
  let binary = '';
  for (let offset = 0; offset < data.length; offset += 8192) binary += String.fromCharCode(...data.subarray(offset, offset+8192));
  return { filename, media_type, content_base64: btoa(binary) };
}
export async function prepareFile(file: File): Promise<UploadedFile> {
  const type = fileMediaType(file.name);
  const limit = type.startsWith('image/') ? MAX_UPLOAD_BYTES : MAX_TEXT_BYTES;
  if (!file.size || file.size > limit) throw new Error(`Select a nonempty file no larger than ${formatBytes(limit)}.`);
  return encodeFile(file.name, new Uint8Array(await file.arrayBuffer()));
}
export function safeSourceURL(value: string): string {
  let url: URL;
  if (/[\s\\]/.test(value)) throw new Error('Use a complete HTTPS URL without spaces or backslashes.');
  try { url = new URL(value); } catch { throw new Error('Use a complete HTTPS URL.'); }
  let decoded: string;
  try { decoded = decodeURIComponent(value); } catch { throw new Error('Use a correctly encoded HTTPS URL.'); }
  if (value.length > 2000 || /[\s\p{Cc}]/u.test(decoded) || url.protocol !== 'https:' || url.username || url.password || url.port && url.port !== '443') {
    throw new Error('Use an HTTPS URL without credentials or a custom port.');
  }
  return value;
}
export function boundedEvidenceBody<T>(body: T): T {
  if (new TextEncoder().encode(JSON.stringify(body)).length > MAX_EVIDENCE_JSON_BYTES) throw new Error('The evidence request is too large. Shorten its metadata or use a smaller artifact.');
  return body;
}
export function evidenceRevisionPath(root: string, id: string, revision: number): string {
  if (!/^\/api\/v1\/workspaces\/[a-f0-9-]{36}\/projects\/[a-f0-9-]{36}\/work-packages\/[a-f0-9-]{36}\/evidence$/i.test(root)
      || !/^[a-f0-9-]{36}$/i.test(id) || !Number.isInteger(revision) || revision < 1 || revision > 50) throw new Error('Invalid local evidence reference.');
  return `${root}/${id}/revisions/${revision}`;
}
export function reviewStateLabel(state: EvidenceCollection['review_state']): string {
  return { not_submitted: 'Not submitted', legacy_without_evidence: 'Earlier submission has no evidence packet',
    current: 'Submission matches the current packet', stale: 'Submission needs fresh evidence review' }[state];
}
