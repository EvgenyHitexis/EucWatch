'use strict';
// Parse each named file as ECMAScript 5 script code (Espruino 2v14 runs no newer syntax).
// Prints `file:line:column: message` for the first newer construct in each failing file.
// scripts/check-es5.py chooses the files; run that, not this.
const fs = require('fs');
const path = require('path');

let acorn;
try {
  acorn = require(require.resolve('acorn', { paths: [path.join(__dirname, '..', 'frontend')] }));
} catch (error) {
  console.error('ES5 check: acorn is not installed; run ./scripts/setup.sh');
  process.exit(2);
}

const files = process.argv.slice(2);
if (!files.length) {
  console.error('ES5 check: no files given');
  process.exit(2);
}
let failed = 0;
for (const file of files) {
  try {
    acorn.parse(fs.readFileSync(file, 'utf8'), { ecmaVersion: 5, sourceType: 'script', locations: true });
  } catch (error) {
    if (!(error instanceof SyntaxError) || !error.loc) throw error;
    failed += 1;
    console.error(`${file}:${error.loc.line}:${error.loc.column + 1}: not ES5: ${error.message.replace(/ \(\d+:\d+\)$/, '')}`);
  }
}
if (failed) {
  console.error(`ES5 check failed: ${failed} of ${files.length} watch modules`);
  process.exit(1);
}
console.log(`ES5 check passed: ${files.length} watch modules`);
