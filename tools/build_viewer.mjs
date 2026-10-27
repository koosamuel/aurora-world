import {build} from 'esbuild';
import {copyFile} from 'node:fs/promises';
await build({entryPoints:['tools/browser/sample-viewer.js'],bundle:true,minify:true,format:'esm',target:'es2022',outfile:'client/vendor/sample-viewer.js',legalComments:'eof'});
await copyFile('node_modules/three/LICENSE','client/vendor/THREE-LICENSE.txt');
