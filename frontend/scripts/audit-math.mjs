// Read-only audit of stored, renderable content. Never prints user text or secrets.
// Run from frontend: node scripts/audit-math.mjs [path-to-data-directory]
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import katex from 'katex';
import { normalizeMath } from '../src/math.ts';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const database = path.join(process.argv[2] ? path.resolve(process.argv[2]) : path.join(root,'data'), 'learnest.sqlite3');
const script = String.raw`
import sqlite3,json,sys,pathlib
p=pathlib.Path(sys.argv[1])
if not p.exists():
    print('[]'); sys.exit(0)
db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
records=[]
for table,cols in [('chapters',['lesson','title']),('questions',['payload']),('attempts',['feedback']),('messages',['text']),('review_maps',['payload']),('review_sessions',['questions','attempts'])]:
    if table not in tables: continue
    for row in db.execute('SELECT id,'+','.join(cols)+' FROM '+table):
        for col,val in zip(cols,row[1:]):
            if not val: continue
            try: val=json.loads(val)
            except (ValueError,TypeError): pass
            records.append({'location':table+':'+row[0]+':'+col,'value':val})
print(json.dumps(records,ensure_ascii=True))
`;
const records = JSON.parse(execFileSync(python, ['-c', script, database], {encoding:'utf8',maxBuffer:64*1024*1024}));
let formulas = 0, fields = 0;
const failures = [];
const unmatched = [];
function audit(value, location) {
  if (Array.isArray(value)) return value.forEach((v,i)=>audit(v,location+'.'+i));
  if (value && typeof value==='object') return Object.entries(value).forEach(([k,v])=>audit(v,location+'.'+k));
  if(typeof value!=='string')return;
  fields++;
  const text = normalizeMath(value).replace(/```math\s*\n([\s\S]*?)```/g, (_,t)=>'$$'+t+'$$').replace(/```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`]*`/g,'');
  for (const match of text.matchAll(/(?<!\\)\$\$([\s\S]*?)(?<!\\)\$\$|(?<!\\)\$([^\n$]+?)(?<!\\)\$/g)) {
    formulas++;
    try { katex.renderToString(match[1]??match[2], {displayMode:match[1]!==undefined,throwOnError:true,trust:false,strict:'ignore',maxExpand:1000}); }
    catch { failures.push({location,formula_index:formulas}); }
  }
  const remaining = text.replace(/(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$|(?<!\\)\$[^\n$]+?(?<!\\)\$/g,'');
  if (/(?<!\\)\\[\[(]|(?<!\\)\$(?!\d)|(?<!\\)\\begin\{/.test(remaining)) unmatched.push(location);
}
records.forEach(r=>audit(r.value,r.location));
console.log(JSON.stringify({records:records.length,fields,formulas,unrenderable:failures.length,locations:failures.slice(0,30),unmatched_math_fields:unmatched.length,unmatched_locations:unmatched.slice(0,30),note:'Read-only; unmatched delimiters are heuristic warnings. No source text is printed.'},null,2));
process.exitCode=failures.length || unmatched.length?1:0;
