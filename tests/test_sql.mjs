// Real PostgreSQL via PGlite; auth/storage schemas are minimal Supabase test doubles.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {PGlite}=await import(process.env.PGLITE_MODULE || '@electric-sql/pglite');
const db=new PGlite();let checks=0;
const query=(s,p=[])=>db.query(s,p);
const f='10000000-0000-4000-8000-000000000001',l='10000000-0000-4000-8000-000000000002',d='20000000-0000-4000-8000-000000000001';
const u='30000000-0000-4000-8000-000000000001',v='30000000-0000-4000-8000-000000000002';
async function role(name,user=''){await db.exec(`reset role; set role ${name};`);await query("select set_config('request.jwt.claim.role',$1,false),set_config('request.jwt.claim.sub',$2,false)",[name,user]);}
async function rejects(fn){await assert.rejects(fn);checks++;}
function ok(value){assert.ok(value);checks++;}
try {
 await db.exec(`create role anon;create role authenticated;create role service_role bypassrls;
 create schema auth;create schema storage;
 create table auth.users(id uuid primary key);
 create function auth.uid() returns uuid language sql as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
 create function auth.role() returns text language sql as $$select current_setting('request.jwt.claim.role',true)$$;
 create table storage.buckets(id text primary key,name text,public boolean);
 create table storage.objects(id uuid primary key default gen_random_uuid(),bucket_id text,name text);
 alter table storage.objects enable row level security;
 create function storage.foldername(text) returns text[] language sql as $$select (string_to_array($1,'/'))[1:array_length(string_to_array($1,'/'),1)-1]$$;
 grant usage on schema public,auth,storage to anon,authenticated,service_role;
 grant select on storage.objects to authenticated;
 `);
 await db.exec(await readFile(new URL('../supabase/migrations/202610260001_core.sql',import.meta.url),'utf8'));
 await db.exec(await readFile(new URL('../supabase/seed.sql',import.meta.url),'utf8'));
 await query('insert into auth.users values($1),($2)',[u,v]);
 await query("insert into public.project_members values($1,$2,'runner'),($3,$4,'viewer')",[f,u,l,v]);
 await query("insert into storage.objects(bucket_id,name) values('aurora-artifacts',$1),('aurora-artifacts',$2)",[f+'/result.json',l+'/private.json']);
 await role('anon');await rejects(()=>query('select * from public.projects'));
 await role('authenticated',u);
 ok((await query('select * from public.projects')).rows.length===1);
 ok((await query('select * from storage.objects')).rows.length===1);
 await rejects(()=>query("insert into public.project_members values($1,$2,'admin')",[l,u]));
 await rejects(()=>query("update public.projects set name='unsafe'"));
 await rejects(()=>query('select public.claim_run()'));
 const request=async(key,config={})=>(await query('select public.request_forecast($1,$2,$3,$4::jsonb) as r',[f,d,key,JSON.stringify(config)])).rows[0].r;
 const first=await request('same');ok((await request('same')).id===first.id);
 await rejects(()=>request('same',{horizon:2}));
 await rejects(()=>request('bad',{horizon:true}));
 await rejects(()=>request('bad',{seed:23}));
 await rejects(()=>query('select public.request_forecast($1,$2,$3)',[l,d,'cross']));
 await role('authenticated',v);
 ok((await query('select * from public.runs')).rows.length===0);
 await rejects(()=>query('select public.request_forecast($1,$2,$3)',[f,d,'outsider']));
 await role('service_role');
 const job=(await query('select public.claim_run() as r')).rows[0].r;ok(job.id===first.id);
 const complete=(token)=>query('select public.complete_run($1,$2,$3::jsonb) as ok',[first.id,token,JSON.stringify({schema_version:'aurora-baseline-v1',synthetic:true})]);
 ok((await complete('40000000-0000-4000-8000-000000000001')).rows[0].ok===false);
 await query("update public.runs set lease_expires_at=now()-interval '1 second' where id=$1",[first.id]);
 const replacement=(await query('select public.claim_run() as r')).rows[0].r;ok(replacement.token!==job.token);
 ok((await complete(job.token)).rows[0].ok===false);
 ok((await complete(replacement.token)).rows[0].ok===true);
 ok((await query('select public.claim_run() as r')).rows[0].r===null);
 await role('authenticated',u);const cancel=await request('cancel');
 ok((await query('select public.request_cancel($1) as ok',[cancel.id])).rows[0].ok);
 await role('service_role');ok((await query('select public.claim_run() as r')).rows[0].r===null);
 console.log(`${checks} PostgreSQL/RLS checks passed (Supabase Auth/Storage test doubles; live service not connected).`);
} finally {await db.close();}
