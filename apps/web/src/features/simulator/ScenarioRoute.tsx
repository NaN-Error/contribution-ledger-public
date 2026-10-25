import { useEffect,useState } from 'react';
import { parseScenarioHash } from '../../lib/simulator.js';
import { SavedScenarioView } from './Simulator.js';

export function ScenarioRoute() {
  const [hash,setHash]=useState(()=>window.location.hash);
  useEffect(()=>{const update=()=>setHash(window.location.hash);window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update);},[]);
  const target=parseScenarioHash(hash);
  if(!target)return <section className="panel"><h1>Invalid scenario link</h1><a className="button" href="#projects">Back to workspaces</a></section>;
  return <><h1>Saved hypothetical scenario</h1><SavedScenarioView key={hash} root={`/api/v1/workspaces/${target.workspaceId}/projects/${target.projectId}`}
    id={target.scenarioId} workspaceId={target.workspaceId} projectId={target.projectId} close={()=>{window.location.hash='#projects';}}/></>;
}
