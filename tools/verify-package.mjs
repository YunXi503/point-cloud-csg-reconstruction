import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'provenance/release-manifest.json'),'utf8'));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const failures=[];
const ignoredDirectories=new Set(['.git','node_modules','.venv','venv','runs','__pycache__','bin','obj']);
function walk(directory){
  const files=[];
  for(const entry of fs.readdirSync(directory,{withFileTypes:true})){
    if(entry.isDirectory()&&ignoredDirectories.has(entry.name))continue;
    const target=path.join(directory,entry.name);
    if(entry.isDirectory())files.push(...walk(target));
    else if(entry.isFile())files.push(path.relative(root,target).replaceAll('\\','/'));
  }
  return files;
}
function inside(base,relative){
  const target=path.resolve(base,relative);
  if(!target.startsWith(path.resolve(base)+path.sep))throw new Error('Unsafe manifest path: '+relative);
  return target;
}
for(const file of manifest.files){
  const target=inside(root,file.path);
  if(!fs.existsSync(target)||hash(target)!==file.sha256)failures.push(file.path);
}
const declared=new Set(manifest.files.map(file=>file.path));
declared.add('provenance/release-manifest.json');
for(const relative of walk(root))if(!declared.has(relative))failures.push('UNLISTED: '+relative);
const args=process.argv.slice(2);
function option(name){const i=args.indexOf(name);return i<0?null:args[i+1];}
const sourceRoot=option('--source-root'),originalRoot=option('--original-csharp-root');
let sourceChecked=0;
for(const file of manifest.copied_sources){
  const base=file.source_root==='thesis_workspace'?sourceRoot:originalRoot;
  if(!base)continue;
  const target=inside(base,file.source_path);
  if(!fs.existsSync(target)||hash(target)!==file.sha256)failures.push('SOURCE: '+file.source_path);
  sourceChecked++;
}
const cases=JSON.parse(fs.readFileSync(path.join(root,'examples/cases.json'),'utf8'));
for(const item of cases)for(const relative of [item.entrypoint,item.input,item.reference_directory]){
  if(!fs.existsSync(inside(root,relative)))failures.push('CASE PATH: '+relative);
}
console.log(JSON.stringify({packaging_version:manifest.packaging_version,package_files_checked:manifest.files.length,
  source_files_checked:sourceChecked,case_paths_checked:cases.length*3,failures},null,2));
if(failures.length)process.exitCode=1;
