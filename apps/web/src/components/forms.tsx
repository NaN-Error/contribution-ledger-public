import { useId, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react';

export function SelectField({ label, children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { label: string; children: ReactNode }) {
  const id = useId();
  return <div className="field"><label htmlFor={id}>{label}</label><select id={id} {...props}>{children}</select></div>;
}
export function TextArea({ label, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string }) {
  const id = useId();
  return <div className="field"><label htmlFor={id}>{label}</label><textarea id={id} {...props} /></div>;
}
export function Feedback({ error, success }: { error?: string | null; success?: string | null }) {
  return <>{error && <div className="error-panel" role="alert"><p>{error}</p></div>}
    {success && <p className="success-note" role="status">{success}</p>}</>;
}
export function Loading({ error, refresh }: { error?: string | null; refresh: () => void }) {
  return error ? <div className="error-panel" role="alert"><p>{error}</p><button className="button" onClick={refresh}>Retry loading</button></div>
    : <p role="status">Loading…</p>;
}
export function Submit({ pending, disabled=false, children }: { pending: boolean; disabled?: boolean; children: ReactNode }) {
  return <button className="button primary" type="submit" disabled={pending||disabled}>{pending ? 'Saving…' : children}</button>;
}
