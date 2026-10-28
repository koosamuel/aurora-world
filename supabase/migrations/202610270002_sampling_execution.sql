-- Authenticated synthetic U20/U21 only; isolated from forecast runs and permissions.
create table public.sampling_briefs (
 id uuid primary key default gen_random_uuid(), project_id uuid not null references public.projects(id),
 product_id text not null, version integer not null check(version>0), checksum text not null check(checksum ~ '^[0-9a-f]{64}$'),
 envelope jsonb not null, source jsonb not null, created_by uuid references auth.users(id), created_at timestamptz not null default now(),
 unique(project_id,product_id,version), check(envelope->'brief'->>'data_kind'='synthetic')
);
create table public.sampling_runs (
 id uuid primary key default gen_random_uuid(),project_id uuid not null references public.projects(id),requested_by uuid not null references auth.users(id),
 kind text not null check(kind in ('validate_brief','geometry','ai')),request_key text not null check(length(request_key) between 8 and 80),
 payload jsonb not null,status text not null default 'queued' check(status in ('queued','running','succeeded','failed','cancelled')),
 attempt integer not null default 0,claim_token uuid,lease_expires_at timestamptz,result jsonb,error text,
 created_at timestamptz not null default now(),updated_at timestamptz not null default now(),unique(project_id,requested_by,request_key)
);
create index sampling_queue on public.sampling_runs(status,created_at);
create index sampling_project_history on public.sampling_runs(project_id,created_at desc);
create table public.sampling_artifacts (
 id uuid primary key default gen_random_uuid(),project_id uuid not null references public.projects(id),run_id uuid not null references public.sampling_runs(id),
 attempt integer not null,name text not null,bucket text not null check(bucket='aurora-sampling'),path text not null,
 sha256 text not null check(sha256 ~ '^[0-9a-f]{64}$'),bytes bigint not null check(bytes between 1 and 16777216),mime text not null,
 unique(run_id,attempt,name),unique(bucket,path)
);
create table public.sampling_workers(worker_id text primary key,last_seen timestamptz not null,ai_available boolean not null);
create function public.sampling_immutable() returns trigger language plpgsql set search_path='' as $$
begin raise exception '불변 명세/실행 입력은 수정할 수 없습니다.';end; $$;
create trigger sampling_brief_no_change before update or delete on public.sampling_briefs for each row execute function public.sampling_immutable();
create trigger sampling_input_no_change before update of project_id,requested_by,kind,request_key,payload,created_at on public.sampling_runs for each row execute function public.sampling_immutable();
alter table public.sampling_briefs enable row level security;
alter table public.sampling_runs enable row level security;
alter table public.sampling_artifacts enable row level security;
alter table public.sampling_workers enable row level security;
create policy sampling_brief_read on public.sampling_briefs for select to authenticated using(public.has_project_role(project_id));
create policy sampling_run_read on public.sampling_runs for select to authenticated using(public.has_project_role(project_id));
create policy sampling_artifact_read on public.sampling_artifacts for select to authenticated using(public.has_project_role(project_id) and exists(select 1 from public.sampling_runs r where r.id=run_id and r.status='succeeded' and r.attempt=sampling_artifacts.attempt));
revoke all on public.sampling_briefs,public.sampling_runs,public.sampling_artifacts,public.sampling_workers from anon,authenticated;
grant select on public.sampling_briefs,public.sampling_runs,public.sampling_artifacts to authenticated;
grant all on public.sampling_briefs,public.sampling_runs,public.sampling_artifacts,public.sampling_workers to service_role;

create function public.request_sampling(p_project_id uuid,p_kind text,p_request_key text,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.sampling_runs;b public.sampling_briefs;k text;body jsonb;
begin
 if not public.has_project_role(p_project_id,array['runner','admin']) then raise exception '샘플 실행 권한이 없습니다.' using errcode='42501';end if;
 if not exists(select 1 from public.projects where id=p_project_id and project_type='labeling') then raise exception '디지털 샘플링 프로젝트가 필요합니다.';end if;
 if p_request_key is null or p_request_key !~ '^[A-Za-z0-9_-]{8,80}$' then raise exception '요청 키 형식 오류';end if;
 if p_payload is null or jsonb_typeof(p_payload)<>'object' or octet_length(p_payload::text)>1100000 then raise exception '입력 크기/형식 오류';end if;
 if p_kind='validate_brief' then
  if p_payload-'raw_brief'<>'{}'::jsonb or jsonb_typeof(p_payload->'raw_brief') is distinct from 'string' or octet_length(p_payload->>'raw_brief') not between 1 and 524288 then raise exception '합성 명세 JSON512KiB 이하 필요';end if;
  body=p_payload;
 elsif p_kind in ('geometry','ai') then
  if p_payload-array['source_id','source_checksum','seed']<>'{}'::jsonb or not(p_payload ?& array['source_id','source_checksum','seed']) or jsonb_typeof(p_payload->'seed') is distinct from 'number' or (p_payload->>'seed')!~'^[0-9]{1,10}$' then raise exception '생성 입력/시드 오류';end if;
  if (p_payload->>'seed')::numeric>2147483647 then raise exception '시드 범위 오류';end if;
  select * into b from public.sampling_briefs where project_id=p_project_id and source->>'id'=p_payload->>'source_id' and source->>'checksum'=p_payload->>'source_checksum';
  if not found then raise exception '등록된 같은 프로젝트의 명세/해시가 필요합니다.';end if;
  body=jsonb_build_object('source',b.source,'seed',p_payload->'seed');
 else raise exception '지원하지 않는 샘플 작업';end if;
 select * into r from public.sampling_runs where project_id=p_project_id and requested_by=auth.uid() and request_key=p_request_key;
 if found then
  if r.kind<>p_kind or r.payload<>body then raise exception '같은 요청 키의 입력이 다릅니다.';end if;
  return jsonb_build_object('id',r.id,'status',r.status);
 end if;
 -- Serialize the bounded project queue and same-key inserts.
 perform 1 from public.projects where id=p_project_id for update;
 select * into r from public.sampling_runs where project_id=p_project_id and requested_by=auth.uid() and request_key=p_request_key;
 if found then
  if r.kind<>p_kind or r.payload<>body then raise exception '같은 요청 키의 입력이 다릅니다.';end if;
  return jsonb_build_object('id',r.id,'status',r.status);
 end if;
 if (select count(*) from public.sampling_runs where project_id=p_project_id and status in ('queued','running'))>=4 then raise exception '진행 중인 샘플 작업은 프로젝트당4개까지입니다.';end if;
 insert into public.sampling_runs(project_id,requested_by,kind,request_key,payload) values(p_project_id,auth.uid(),p_kind,p_request_key,body) returning * into r;
 return jsonb_build_object('id',r.id,'status',r.status);
end; $$;

create function public.register_sampling_brief(p_project_id uuid,p_validation_run uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.sampling_runs;b public.sampling_briefs;prev public.sampling_briefs;env jsonb;src jsonb;p jsonb;
begin
 if not public.has_project_role(p_project_id,array['runner','admin']) then raise exception '명세 등록 권한이 없습니다.' using errcode='42501';end if;
 perform 1 from public.projects where id=p_project_id and project_type='labeling' for update;
 if not found then raise exception '샘플링 프로젝트 필요';end if;
 select * into r from public.sampling_runs where id=p_validation_run and project_id=p_project_id and kind='validate_brief' and status='succeeded';
 if not found then raise exception '서버 검증을 완료한 명세가 필요합니다.';end if;
 env=r.result->'envelope';src=r.result->'source';p=env->'brief';
 select * into b from public.sampling_briefs where project_id=p_project_id and product_id=p->>'product_id' and version=(p->>'brief_version')::int;
 if found then
  if b.checksum<>env->>'checksum' then raise exception '같은 제품/버전 덮어쓰기 금지';end if;
  return b.envelope||jsonb_build_object('reused',true);
 end if;
 select * into prev from public.sampling_briefs where project_id=p_project_id and product_id=p->>'product_id' order by version desc limit 1;
 if found then
  if (p->>'brief_version')::int<>prev.version+1 or p->>'previous_checksum' is distinct from prev.checksum then raise exception '최신 부모 버전/해시 충돌';end if;
  if (p->>'artwork_version')::int<>(prev.envelope->'brief'->>'artwork_version')::int+(case when prev.envelope->'brief'->'artwork'<>p->'artwork' then 1 else 0 end) then raise exception '원화 버전 충돌';end if;
 elsif (p->>'brief_version')::int<>1 or (p->>'artwork_version')::int<>1 then raise exception '새 명세는 버전1부터';end if;
 insert into public.sampling_briefs(project_id,product_id,version,checksum,envelope,source,created_by) values(p_project_id,p->>'product_id',(p->>'brief_version')::int,env->>'checksum',env,src,auth.uid()) returning * into b;
 return b.envelope||jsonb_build_object('registered_at',b.created_at,'reused',false);
end; $$;

create function public.claim_sampling() returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.sampling_runs;
begin
 if auth.role() is distinct from 'service_role' then raise exception '워커 전용' using errcode='42501';end if;
 update public.sampling_runs set status='failed',error='재시도 한도 초과',updated_at=now() where status='running' and lease_expires_at<now() and attempt>=3;
 select * into r from public.sampling_runs where attempt<3 and (status='queued' or (status='running' and lease_expires_at<now())) order by created_at limit 1 for update skip locked;
 if not found then return null;end if;
 update public.sampling_runs set status='running',attempt=attempt+1,claim_token=gen_random_uuid(),lease_expires_at=now()+interval '120 seconds',updated_at=now() where id=r.id returning * into r;
 return to_jsonb(r);
end; $$;
create function public.heartbeat_sampling(p_run_id uuid,p_token uuid) returns boolean language plpgsql security definer set search_path='' as $$
declare n int;
begin
 if auth.role() is distinct from 'service_role' then raise exception '워커 전용' using errcode='42501';end if;
 update public.sampling_runs set lease_expires_at=now()+interval '120 seconds',updated_at=now() where id=p_run_id and claim_token=p_token and status='running' and lease_expires_at>=now();get diagnostics n=row_count;return n=1;
end; $$;
create function public.complete_sampling(p_run_id uuid,p_token uuid,p_result jsonb default null,p_artifacts jsonb default '[]',p_error text default null)
returns boolean language plpgsql security definer set search_path='' as $$
declare r public.sampling_runs;a jsonb;names text[];expected text[];
begin
 if auth.role() is distinct from 'service_role' then raise exception '워커 전용' using errcode='42501';end if;
 select * into r from public.sampling_runs where id=p_run_id and claim_token=p_token and status='running' and lease_expires_at>=now() for update;
 if not found then return false;end if;
 if p_error is not null then update public.sampling_runs set status='failed',result=null,error=left(p_error,300),updated_at=now() where id=r.id;return true;end if;
 if p_result is null or jsonb_typeof(p_result)<>'object' then raise exception '결과 객체 필요';end if;
 if r.kind='validate_brief' then
  if p_result->'envelope'->'brief' is distinct from (r.payload->>'raw_brief')::jsonb or p_result->'envelope'->'brief'->>'data_kind' is distinct from 'synthetic' or coalesce(p_result->'envelope'->>'checksum','') !~ '^[0-9a-f]{64}$' or p_result->'source'->>'brief_checksum' is distinct from p_result->'envelope'->>'checksum' or p_artifacts<>'[]'::jsonb then raise exception '검증 명세/해시 오류';end if;
 else
  if p_result->'report'->>'source_checksum' is distinct from r.payload->'source'->>'checksum' or p_result->'report'->'seed' is distinct from r.payload->'seed' or p_result->'report'->>'schema_version' is distinct from (case when r.kind='geometry' then 'aurora-digital-sample-v1' else 'aurora-ai-sample-v1' end) then raise exception '생성 결과 입력/설정 오류';end if;
  expected=case when r.kind='geometry' then array['input.json','baseline.glb','baseline.front.svg','baseline.side.svg','candidate.glb','candidate.front.svg','candidate.side.svg','report.json','comparison.md','artifacts.json'] else array['input.json','input.png','preserve.png','reinterpret.png','analysis.json','report.json','models.json','artifacts.json'] end;
  if jsonb_typeof(p_artifacts) is distinct from 'array' or jsonb_array_length(p_artifacts)<>cardinality(expected) or jsonb_array_length(p_result->'artifacts')<>cardinality(expected) then raise exception '산출물 수 오류';end if;
  names=array[]::text[];
  for a in select value from jsonb_array_elements(p_artifacts) loop
   if a->>'name' is null or not(a->>'name'=any(expected)) or a->>'name'=any(names) or a->>'bucket' is distinct from 'aurora-sampling' or a->>'sha256' is null or a->>'sha256' !~ '^[0-9a-f]{64}$' or (a->>'bytes')::bigint not between 1 and 16777216 or a->>'path' is distinct from r.project_id::text||'/sampling/'||r.id::text||'/attempt-'||r.attempt||'/'||(a->>'sha256')||'/'||(a->>'name') then raise exception '산출물 경로/메타데이터 오류';end if;
   if a->>'mime' is distinct from (case when a->>'name' like '%.glb' then 'model/gltf-binary' when a->>'name' like '%.svg' then 'image/svg+xml' when a->>'name' like '%.png' then 'image/png' when a->>'name' like '%.md' then 'text/markdown' else 'application/json' end) then raise exception '산출물 MIME 오류';end if;
   if not exists(select 1 from jsonb_array_elements(p_result->'artifacts') x where x->>'file'=a->>'name' and x->>'sha256'=a->>'sha256' and x->>'bytes'=a->>'bytes') or not exists(select 1 from storage.objects o where o.bucket_id='aurora-sampling' and o.name=a->>'path') then raise exception '업로드/결과 산출물 불일치';end if;
   names=array_append(names,a->>'name');
   insert into public.sampling_artifacts(project_id,run_id,attempt,name,bucket,path,sha256,bytes,mime) values(r.project_id,r.id,r.attempt,a->>'name',a->>'bucket',a->>'path',a->>'sha256',(a->>'bytes')::bigint,a->>'mime');
  end loop;
 end if;
 update public.sampling_runs set status='succeeded',result=p_result,error=null,updated_at=now() where id=r.id;return true;
end; $$;
create function public.cancel_sampling(p_run_id uuid) returns boolean language plpgsql security definer set search_path='' as $$
declare r public.sampling_runs;n int;
begin
 select * into r from public.sampling_runs where id=p_run_id;
 if not found or not public.has_project_role(r.project_id,array['runner','admin']) or not(r.requested_by=auth.uid() or public.has_project_role(r.project_id,array['admin'])) then raise exception '취소 권한 없음' using errcode='42501';end if;
 update public.sampling_runs set status='cancelled',updated_at=now() where id=r.id and status in ('queued','running');get diagnostics n=row_count;return n=1;
end; $$;
create function public.sampling_download(p_artifact_id uuid) returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.sampling_artifacts;
begin
 select x.* into a from public.sampling_artifacts x join public.sampling_runs r on r.id=x.run_id and r.project_id=x.project_id and r.attempt=x.attempt where x.id=p_artifact_id and r.status='succeeded' and public.has_project_role(x.project_id);
 if not found then raise exception '다운로드 권한 없음' using errcode='42501';end if;return to_jsonb(a);
end; $$;
create function public.sampling_worker_beat(p_worker_id text,p_ai_available boolean) returns boolean language plpgsql security definer set search_path='' as $$
begin
 if auth.role() is distinct from 'service_role' then raise exception '워커 전용' using errcode='42501';end if;
 if p_worker_id !~ '^[a-z0-9-]{1,80}$' or p_ai_available is null then raise exception '워커 상태 오류';end if;
 insert into public.sampling_workers values(p_worker_id,now(),p_ai_available) on conflict(worker_id) do update set last_seen=now(),ai_available=excluded.ai_available;return true;
end; $$;
create function public.sampling_worker_status(p_project_id uuid) returns jsonb language plpgsql security definer set search_path='' as $$
begin
 if not public.has_project_role(p_project_id) then raise exception '열람 권한 없음' using errcode='42501';end if;
 return jsonb_build_object('online',exists(select 1 from public.sampling_workers where last_seen>now()-interval '60 seconds'),'ai_available',exists(select 1 from public.sampling_workers where last_seen>now()-interval '60 seconds' and ai_available));
end; $$;
revoke all on function public.request_sampling(uuid,text,text,jsonb),public.register_sampling_brief(uuid,uuid),public.cancel_sampling(uuid),public.sampling_download(uuid),public.sampling_worker_status(uuid) from public,anon;
grant execute on function public.request_sampling(uuid,text,text,jsonb),public.register_sampling_brief(uuid,uuid),public.cancel_sampling(uuid),public.sampling_download(uuid),public.sampling_worker_status(uuid) to authenticated;
revoke all on function public.claim_sampling(),public.heartbeat_sampling(uuid,uuid),public.complete_sampling(uuid,uuid,jsonb,jsonb,text),public.sampling_worker_beat(text,boolean) from public,anon,authenticated;
grant execute on function public.claim_sampling(),public.heartbeat_sampling(uuid,uuid),public.complete_sampling(uuid,uuid,jsonb,jsonb,text),public.sampling_worker_beat(text,boolean) to service_role;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values('aurora-sampling','aurora-sampling',false,16777216,array['application/json','model/gltf-binary','image/svg+xml','image/png','text/markdown']);
create policy sampling_storage_read on storage.objects for select to authenticated using(bucket_id='aurora-sampling' and exists(select 1 from public.sampling_artifacts a join public.sampling_runs r on r.id=a.run_id and r.project_id=a.project_id and r.attempt=a.attempt where a.bucket=storage.objects.bucket_id and a.path=storage.objects.name and r.status='succeeded' and public.has_project_role(a.project_id)));
