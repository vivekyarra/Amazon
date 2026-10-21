/** Capture an actual authenticated browser session. Password entry is outside the recording. */
import { chromium } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
const directory='artifacts/demo';
await mkdir(directory+'/frames',{recursive:true});
const credentials=JSON.parse(await readFile((process.env.DATA_DIR||'.local')+'/access.json','utf8'));
const browser=await chromium.launch({headless:true,...(process.env.CI?{}:{executablePath:'/usr/bin/chromium',args:['--no-sandbox']})});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
let capturing=true;
const frames=[];
try {
 await page.goto(process.env.DEMO_BASE_URL||'http://127.0.0.1:8080');
 await page.getByLabel('Password',{exact:true}).fill(credentials['demo-admin']);
 await page.getByRole('button',{name:'Open mission control'}).click();
 await page.getByRole('heading',{name:'Mission control.'}).waitFor();
 await Promise.all([page.waitForResponse(r=>r.url().endsWith('/api/admin/reset')),page.getByRole('button',{name:'Reset day'}).click()]);
 const capture=(async()=>{try { while(capturing){const path=`${directory}/frames/frame-${String(frames.length).padStart(5,'0')}.jpg`;await page.screenshot({path,type:'jpeg',quality:82});frames.push({path,at:Date.now()});await new Promise(r=>setTimeout(r,240));}} catch(error) { if(capturing) throw error; } })();
 await page.waitForTimeout(1800);
 await page.getByRole('button',{name:'Run the full day',exact:true}).click();
 await page.getByText('Promise kept. Evidence saved.',{exact:true}).waitFor({timeout:90000}); console.log('Recorded canonical day / pose completion');
 await page.waitForTimeout(1800);
 await page.getByRole('button',{name:/^Evidence & incidents/}).click();
 await page.waitForTimeout(2200);
 await page.getByRole('button',{name:'Review evidence / Prepare report'}).click();
 await page.waitForTimeout(1500);
 await page.getByRole('button',{name:'Review report'}).click();
 await page.waitForTimeout(1800);
 await page.getByRole('button',{name:'Close approval'}).click();
 await page.getByRole('button',{name:'Commitment ledger',exact:true}).click();
 await page.getByRole('button',{name:/Call your sister/}).click();
 await page.waitForTimeout(2000);
 await page.getByRole('button',{name:'Connections & privacy',exact:true}).click();
 await page.waitForTimeout(2200);
 capturing=false;
 await capture;
 const lines=[];
 for(let i=0;i<frames.length;i++){lines.push(`file 'frames/${frames[i].path.split('/').at(-1)}'`);lines.push(`duration ${i<frames.length-1?(frames[i+1].at-frames[i].at)/1000:.25}`);}
 await writeFile(directory+'/frames.ffconcat',lines.join('\n')+'\n');
 const result=spawnSync('ffmpeg',['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',directory+'/frames.ffconcat','-vf','scale=1440:1000','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',directory+'/done-irl-browser-demo.mp4'],{stdio:'inherit'});
 if(result.status!==0)throw new Error('Video encoding failed');
 console.log(`Captured ${frames.length} real browser frames. This is synthetic-mode web footage, not Fire TV runtime proof.`);
} catch(error) { console.error("Browser capture failed:", error.message); process.exitCode=1; } finally {capturing=false;await new Promise(r=>setTimeout(r,350));await browser.close();}
