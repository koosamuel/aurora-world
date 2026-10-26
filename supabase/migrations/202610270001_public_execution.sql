-- Public observed invoice inputs remain private; only aggregate preview is published.
alter table public.datasets drop constraint datasets_synthetic_check;
alter table public.datasets add column dataset_kind text not null default 'synthetic';
alter table public.datasets add constraint dataset_kind_check check (
 (dataset_kind='synthetic' and synthetic) or
 (dataset_kind='public_retail' and not synthetic and generator_config->>'mode' is not distinct from 'public_file_v1'));

create table public.artifacts (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.projects(id),
 run_id uuid not null references public.runs(id),
 attempt integer not null check(attempt>0),
 name text not null check(name in ('result.json','forecast.csv','inventory.csv','decisions.csv','report.md')),
 bucket text not null default 'aurora-artifacts' check(bucket='aurora-artifacts'),
 path text not null unique,
 sha256 text not null check(sha256 ~ '^[0-9a-f]{64}$'),
 bytes bigint not null check(bytes between 1 and 50331648),
 mime text not null check(mime in ('application/json','text/csv','text/markdown')),
 created_at timestamptz not null default now(),
 unique(run_id,attempt,name)
);
alter table public.artifacts enable row level security;
create policy artifact_read on public.artifacts for select to authenticated using (
 public.has_project_role(project_id) and exists(select 1 from public.runs r
 where r.id=run_id and r.project_id=artifacts.project_id and r.status='succeeded' and r.attempt=artifacts.attempt));
revoke all on public.artifacts from anon,authenticated;
grant select on public.artifacts to authenticated;
grant all on public.artifacts to service_role;
create index artifacts_run on public.artifacts(run_id,attempt);
create table public.artifact_download_requests (
 id uuid primary key default gen_random_uuid(),artifact_id uuid not null references public.artifacts(id),
 user_id uuid not null references auth.users(id),requested_at timestamptz not null default now()
);
alter table public.artifact_download_requests enable row level security;
revoke all on public.artifact_download_requests from anon,authenticated;
grant all on public.artifact_download_requests to service_role;

create or replace function public.request_forecast(p_project_id uuid,p_dataset_id uuid,p_idempotency_key text,p_config jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare d public.datasets; r public.runs; c jsonb; k text; hi int;
begin
 if not public.has_project_role(p_project_id,array['runner','admin']) then raise exception '실행 권한이 없습니다.' using errcode='42501'; end if;
 if not exists(select 1 from public.projects where id=p_project_id and project_type='forecast') then raise exception '수요예측 프로젝트가 필요합니다.'; end if;
 select * into d from public.datasets where id=p_dataset_id and project_id=p_project_id and status='ready';
 if not found then raise exception '같은 프로젝트의 준비된 데이터셋이 필요합니다.'; end if;
 if p_idempotency_key is null or length(p_idempotency_key) not between 1 and 120 then raise exception '요청 키를 확인하세요.'; end if;
 if p_config is null or jsonb_typeof(p_config)<>'object' then raise exception '설정 객체가 필요합니다.'; end if;
 if d.dataset_kind='public_retail' then
  for k in select jsonb_object_keys(p_config) loop
   if k<>'policy_inputs' then raise exception '공개 거래는 고정 평가 분할과 정책 입력만 허용합니다.'; end if;
  end loop;
  c='{"policy_inputs":{}}'::jsonb || p_config;
  if jsonb_typeof(c->'policy_inputs')<>'object' or octet_length(c::text)>65536 then raise exception '품목별 정책 JSON을 확인하세요.'; end if;
 else
  for k in select jsonb_object_keys(p_config) loop
   if k not in ('horizon','season_length','validation_origins') then raise exception '허용되지 않은 설정입니다.'; end if;
  end loop;
  c='{"horizon":4,"season_length":52,"validation_origins":3}'::jsonb || p_config;
  foreach k in array array['horizon','season_length','validation_origins'] loop
   hi=case k when 'horizon' then 12 when 'season_length' then 104 else 5 end;
   if jsonb_typeof(c->k)<>'number' or (c->>k)!~'^[0-9]+$' then raise exception '설정은 정수여야 합니다.'; end if;
   if (c->>k)::numeric<1 or (c->>k)::numeric>hi then raise exception '설정 범위를 확인하세요.'; end if;
  end loop;
  if (d.generator_config->>'weeks')::int <= (c->>'horizon')::int*((c->>'validation_origins')::int+1) then raise exception '평가 이력이 부족합니다.'; end if;
 end if;
 insert into public.runs(project_id,dataset_id,requested_by,task_type,idempotency_key,config)
 values(p_project_id,p_dataset_id,auth.uid(),'forecast',p_idempotency_key,c)
 on conflict(project_id,requested_by,idempotency_key) do nothing;
 select * into r from public.runs where project_id=p_project_id and requested_by=auth.uid() and idempotency_key=p_idempotency_key;
 if r.dataset_id<>p_dataset_id or r.config<>c then raise exception '같은 요청 키의 데이터/설정이 다릅니다.'; end if;
 return jsonb_build_object('id',r.id,'status',r.status,'project_id',r.project_id);
end; $$;

create or replace function public.complete_run(p_run_id uuid,p_token uuid,p_result jsonb default null,p_error text default null)
returns boolean language plpgsql security definer set search_path='' as $$
declare n int;
begin
 if auth.role() is distinct from 'service_role' then raise exception '워커 전용 요청입니다.' using errcode='42501'; end if;
 if p_error is null and (p_result is null or p_result->>'schema_version' is distinct from 'aurora-baseline-v1'
   or p_result->'synthetic' is distinct from 'true'::jsonb
   or not exists(select 1 from public.runs r join public.datasets d on d.id=r.dataset_id where r.id=p_run_id and d.synthetic)) then raise exception '합성 기준선 결과가 필요합니다.'; end if;
 update public.runs set status=case when p_error is null then 'succeeded' else 'failed' end,
 result=case when p_error is null then p_result else null end,error=left(p_error,500),updated_at=now()
 where id=p_run_id and claim_token=p_token and status='running' and lease_expires_at>=now();
 get diagnostics n=row_count;return n=1;
end; $$;

create function public.complete_public_run(p_run_id uuid,p_token uuid,p_result jsonb,p_artifacts jsonb)
returns boolean language plpgsql security definer set search_path='' as $$
declare r public.runs; a jsonb; names text[]='{}'; expected_path text; expected_mime text;
begin
 if auth.role() is distinct from 'service_role' then raise exception '워커 전용 요청입니다.' using errcode='42501'; end if;
 select * into r from public.runs where id=p_run_id and claim_token=p_token and status='running' and lease_expires_at>=now() for update;
 if not found then return false; end if;
 if not exists(select 1 from public.datasets d where d.id=r.dataset_id and d.project_id=r.project_id and d.dataset_kind='public_retail') then raise exception '공개 거래 실행이 아닙니다.'; end if;
 if p_result is null or p_result->>'schema_version' is distinct from 'aurora-public-evaluation-v1' or p_result->'synthetic' is distinct from 'false'::jsonb or p_result->'inventory_is_scenario' is distinct from 'true'::jsonb or octet_length(p_result::text)>1048576 then raise exception '공개 거래 요약 결과를 확인하세요.'; end if;
 if p_artifacts is null or jsonb_typeof(p_artifacts)<>'array' or jsonb_array_length(p_artifacts)<>5 then raise exception '필수 산출물 5개가 필요합니다.'; end if;
 for a in select value from jsonb_array_elements(p_artifacts) loop
  if jsonb_typeof(a)<>'object' or a->>'name' is null or a->>'name' not in ('result.json','forecast.csv','inventory.csv','decisions.csv','report.md') or (a->>'name')=any(names) then raise exception '산출물 이름/중복을 확인하세요.'; end if;
  names=array_append(names,a->>'name');
  expected_path=r.project_id::text||'/runs/'||r.id::text||'/attempt-'||r.attempt::text||'/'||(a->>'sha256')||'/'||(a->>'name');
  expected_mime=case when a->>'name'='result.json' then 'application/json' when a->>'name'='report.md' then 'text/markdown' else 'text/csv' end;
  if a->>'bucket' is distinct from 'aurora-artifacts' or a->>'path' is distinct from expected_path or a->>'mime' is distinct from expected_mime or a->>'sha256' is null or (a->>'sha256')!~'^[0-9a-f]{64}$' or (a->>'bytes') is null or (a->>'bytes')!~'^[0-9]+$' then raise exception '산출물 경로/유형/해시/크기를 확인하세요.'; end if;
  if not exists(select 1 from storage.objects where bucket_id='aurora-artifacts' and name=expected_path) then raise exception '저장된 산출물이 없습니다.'; end if;
  insert into public.artifacts(project_id,run_id,attempt,name,bucket,path,sha256,bytes,mime)
  values(r.project_id,r.id,r.attempt,a->>'name',a->>'bucket',a->>'path',a->>'sha256',(a->>'bytes')::bigint,a->>'mime');
 end loop;
 update public.runs set status='succeeded',result=p_result,error=null,updated_at=now() where id=r.id;
 return true;
end; $$;
revoke all on function public.complete_public_run(uuid,uuid,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.complete_public_run(uuid,uuid,jsonb,jsonb) to service_role;

create function public.request_artifact_download(p_artifact_id uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.artifacts;
begin
 select x.* into a from public.artifacts x join public.runs r on r.id=x.run_id and r.project_id=x.project_id and r.attempt=x.attempt
 where x.id=p_artifact_id and r.status='succeeded' and public.has_project_role(x.project_id);
 if not found then raise exception '산출물 접근 권한이 없습니다.' using errcode='42501'; end if;
 insert into public.artifact_download_requests(artifact_id,user_id) values(a.id,auth.uid());
 return to_jsonb(a);
end; $$;
revoke all on function public.request_artifact_download(uuid) from public,anon;
grant execute on function public.request_artifact_download(uuid) to authenticated;

-- Existing registered inputs remain readable; result objects require a published,
-- current-attempt artifact entry. No new client write grants.
drop policy aurora_artifacts_read on storage.objects;
create policy aurora_artifacts_read on storage.objects for select to authenticated using (
 bucket_id='aurora-artifacts' and (
  (name ~ '^[0-9a-f-]{36}/inputs/[0-9a-f]{64}\.json$' and exists(select 1 from public.project_members m where m.user_id=auth.uid() and m.project_id::text=(storage.foldername(name))[1]))
  or exists(select 1 from public.artifacts a join public.runs r on r.id=a.run_id and r.project_id=a.project_id and r.attempt=a.attempt
    where a.path=storage.objects.name and a.bucket=storage.objects.bucket_id and r.status='succeeded' and public.has_project_role(a.project_id))));
update storage.buckets set file_size_limit=50331648,allowed_mime_types=array['application/json','text/csv','text/markdown'] where id='aurora-artifacts';
