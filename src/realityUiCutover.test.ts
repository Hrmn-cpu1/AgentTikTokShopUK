import {describe,expect,it} from 'vitest';import fs from 'node:fs';import path from 'node:path';
describe('reality UI cutover',()=>{it('does not ship demo opportunity fixtures',()=>{const app=fs.readFileSync(path.resolve('src/App.tsx'),'utf8');for(const value of ['Viral Beauty Gadget','Smart LED Lamp','Mini Massage Gun','£73.40','Demo-first creative test'])expect(app).not.toContain(value)})});
