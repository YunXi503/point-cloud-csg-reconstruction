import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const read=rel=>JSON.parse(fs.readFileSync(path.join(root,rel),'utf8'));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const sources=read('provenance/copied-sources.json');
const release=read('provenance/source-versions.json');
const version=release.packaging_version;
for(const f of sources){
  if(hash(path.join(root,f.path))!==f.sha256)throw new Error('Recorded research source changed; review provenance before resealing: '+f.path);
}
for(const item of read('examples/cases.json')){
  if(hash(path.join(root,item.entrypoint))!==item.recorded_program_sha256||hash(path.join(root,item.input))!==item.recorded_input_sha256)
    throw new Error('Recorded case source/input changed: '+item.id);
}
const skip=new Set(['.git','node_modules','.venv','venv','runs','__pycache__','bin','obj']);
function walk(dir){const out=[];for(const e of fs.readdirSync(dir,{withFileTypes:true})){if(e.isDirectory()&&skip.has(e.name))continue;const p=path.join(dir,e.name);if(e.isDirectory())out.push(...walk(p));else if(e.isFile())out.push(p);}return out;}
const files=walk(root).filter(p=>path.relative(root,p).replaceAll('\\','/')!=='provenance/release-manifest.json').map(p=>({path:path.relative(root,p).replaceAll('\\','/'),bytes:fs.statSync(p).size,sha256:hash(p)})).sort((a,b)=>a.path.localeCompare(b.path,'en'));
for(const f of files){if(/\.(exe|dll|pdb|pyc|blend1|blend2)$/i.test(f.path)||/(^|\/)\.env(?:\.|$)/.test(f.path))throw new Error('Release contains a generated binary or environment file: '+f.path);}
fs.writeFileSync(path.join(root,'provenance/release-manifest.json'),JSON.stringify({packaging_version:version,date:release.date,manifest_excludes:['provenance/release-manifest.json'],copied_sources:sources,files},null,2)+'\n');
console.log(JSON.stringify({version,files:files.length+1,protected_sources:sources.length}));
