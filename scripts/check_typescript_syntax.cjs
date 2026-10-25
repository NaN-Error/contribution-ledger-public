/** Optional syntax-only check using installed TypeScript, never presented as a full typecheck. */
const fs = require('node:fs');
const path = require('node:path');
const ts = require(process.env.CL_TYPESCRIPT_PATH || 'typescript');
const root = path.resolve(__dirname, '../apps/web/src');
let count = 0;
function visit(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) visit(filename);
    else if (/\.tsx?$/.test(entry.name)) {
      const result = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { fileName: filename, reportDiagnostics: true,
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX, isolatedModules: true }});
      const errors = (result.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error);
      if (errors.length) { console.error(ts.formatDiagnosticsWithColorAndContext(errors, { getCanonicalFileName: x => x, getCurrentDirectory: () => process.cwd(), getNewLine: () => '\n' })); process.exitCode = 1; }
      count++;
    }
  }
}
visit(root);
console.log(`Checked ${count} TypeScript/TSX files for transpilation syntax only. Run npm run typecheck for semantic checking.`);
