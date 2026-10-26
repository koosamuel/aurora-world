-- Initial skeleton: synthetic datasets, project isolation, fenced forecast jobs.
create table public.projects (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  project_type text not null check (project_type in ('forecast','labeling')),
  created_at timestamptz not null default now()
);
create table public.project_members (
  project_id uuid not null references public.projects(id),
  user_id uuid not null references auth.users(id),
  role text not null check (role in ('viewer','runner','admin')),
  primary key(project_id,user_id)
);
create table public.datasets (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id),
  name text not null,
  version text not null,
  synthetic boolean not null default true check (synthetic),
  status text not null check (status in ('uploaded','validating','ready','rejected')),
  generator_config jsonb not null,
  created_at timestamptz not null default now(),
  unique(project_id,version)
);
create table public.runs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id),
  dataset_id uuid not null references public.datasets(id),
  requested_by uuid not null references auth.users(id),
  task_type text not null check(task_type='forecast'),
  idempotency_key text not null check(length(idempotency_key) between 1 and 120),
  config jsonb not null,
  status text not null default 'queued' check(status in ('queued','running','succeeded','failed','cancelled')),
  attempt integer not null default 0,
  claim_token uuid,
  lease_expires_at timestamptz,
  result jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(project_id,requested_by,idempotency_key)
);
create index runs_project_created on public.runs(project_id,created_at desc);
create index runs_queue on public.runs(status,created_at);
create index members_user on public.project_members(user_id,project_id);
create index datasets_project on public.datasets(project_id,status);

create function public.has_project_role(p_project_id uuid, p_roles text[] default array['viewer','runner','admin'])
returns boolean language sql stable security definer set search_path='' as $$
 select auth.uid() is not null and exists (
   select 1 from public.project_members m where m.project_id=p_project_id
   and m.user_id=auth.uid() and m.role=any(p_roles)
 );
$$;
revoke all on function public.has_project_role(uuid,text[]) from public,anon;
grant execute on function public.has_project_role(uuid,text[]) to authenticated,service_role;

alter table public.projects enable row level security;
alter table public.project_members enable row level security;
alter table public.datasets enable row level security;
alter table public.runs enable row level security;
create policy project_read on public.projects for select to authenticated
 using (public.has_project_role(id));
create policy member_read on public.project_members for select to authenticated
 using (user_id=auth.uid());
create policy dataset_read on public.datasets for select to authenticated
 using (public.has_project_role(project_id));
create policy run_read on public.runs for select to authenticated
 using (public.has_project_role(project_id));
revoke all on public.projects,public.project_members,public.datasets,public.runs from anon,authenticated;
grant select on public.projects,public.project_members,public.datasets,public.runs to authenticated;
grant all on public.projects,public.project_members,public.datasets,public.runs to service_role;

create function public.request_forecast(p_project_id uuid,p_dataset_id uuid,p_idempotency_key text,p_config jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare d public.datasets; r public.runs; c jsonb; k text; lo int; hi int;
begin
 if not public.has_project_role(p_project_id,array['runner','admin']) then
  raise exception '실행 권한이 없습니다.' using errcode='42501';
 end if;
 if not exists(select 1 from public.projects where id=p_project_id and project_type='forecast') then
  raise exception '수요예측 프로젝트만 실행할 수 있습니다.';
 end if;
 select * into d from public.datasets where id=p_dataset_id and project_id=p_project_id and status='ready' and synthetic;
 if not found then raise exception '같은 프로젝트의 준비된 합성 데이터셋이 필요합니다.'; end if;
 if p_idempotency_key is null or length(p_idempotency_key) not between 1 and 120 then raise exception '요청 키를 확인하세요.'; end if;
 if p_config is null or jsonb_typeof(p_config)<>'object' then raise exception '설정 객체가 필요합니다.'; end if;
 for k in select jsonb_object_keys(p_config) loop
  if k not in ('horizon','season_length','validation_origins') then raise exception '허용되지 않은 설정입니다.'; end if;
 end loop;
 c='{"horizon":4,"season_length":52,"validation_origins":3}'::jsonb || p_config;
 foreach k in array array['horizon','season_length','validation_origins'] loop
  lo=1; hi=case k when 'horizon' then 12 when 'season_length' then 104 else 5 end;
  if jsonb_typeof(c->k)<>'number' or (c->>k)!~'^[0-9]+$' then raise exception '설정은 정수여야 합니다.'; end if;
  if (c->>k)::numeric<lo or (c->>k)::numeric>hi then raise exception '설정 범위를 확인하세요.'; end if;
 end loop;
 if (d.generator_config->>'weeks')::int <= (c->>'horizon')::int*((c->>'validation_origins')::int+1) then
  raise exception '평가를 위한 이력이 부족합니다.';
 end if;
 insert into public.runs(project_id,dataset_id,requested_by,task_type,idempotency_key,config)
 values(p_project_id,p_dataset_id,auth.uid(),'forecast',p_idempotency_key,c)
 on conflict(project_id,requested_by,idempotency_key) do nothing;
 select * into r from public.runs where project_id=p_project_id and requested_by=auth.uid() and idempotency_key=p_idempotency_key;
 if r.dataset_id<>p_dataset_id or r.config<>c then raise exception '같은 요청 키의 데이터/설정이 다릅니다.'; end if;
 return jsonb_build_object('id',r.id,'status',r.status,'project_id',r.project_id);
end;
$$;
revoke all on function public.request_forecast(uuid,uuid,text,jsonb) from public,anon;
grant execute on function public.request_forecast(uuid,uuid,text,jsonb) to authenticated;

create function public.claim_run()
returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.runs;
begin
 if auth.role() is distinct from 'service_role' then raise exception '워커 전용 요청입니다.' using errcode='42501'; end if;
 update public.runs set status='failed',error='재시도 한도 초과',updated_at=now()
 where status='running' and lease_expires_at<now() and attempt>=3;
 select * into r from public.runs where task_type='forecast' and attempt<3
 and (status='queued' or (status='running' and lease_expires_at<now()))
 order by created_at limit 1 for update skip locked;
 if not found then return null; end if;
 update public.runs set status='running',attempt=attempt+1,claim_token=gen_random_uuid(),
 lease_expires_at=now()+interval '120 seconds',updated_at=now() where id=r.id returning * into r;
 return jsonb_build_object('id',r.id,'token',r.claim_token,'attempt',r.attempt,'task_type',r.task_type,
 'config',r.config,'generator_config',(select generator_config from public.datasets where id=r.dataset_id));
end;
$$;
create function public.heartbeat_run(p_run_id uuid,p_token uuid)
returns boolean language plpgsql security definer set search_path='' as $$
declare n int;
begin
 if auth.role() is distinct from 'service_role' then raise exception '워커 전용 요청입니다.' using errcode='42501'; end if;
 update public.runs set lease_expires_at=now()+interval '120 seconds',updated_at=now()
 where id=p_run_id and claim_token=p_token and status='running' and lease_expires_at>=now();
 get diagnostics n=row_count; return n=1;
end;
$$;
create function public.complete_run(p_run_id uuid,p_token uuid,p_result jsonb default null,p_error text default null)
returns boolean language plpgsql security definer set search_path='' as $$
declare n int;
begin
 if auth.role() is distinct from 'service_role' then raise exception '워커 전용 요청입니다.' using errcode='42501'; end if;
 if p_error is null and (p_result is null or p_result->>'schema_version' is distinct from 'aurora-baseline-v1'
   or p_result->'synthetic' is distinct from 'true'::jsonb) then raise exception '합성 기준선 결과가 필요합니다.'; end if;
 update public.runs set status=case when p_error is null then 'succeeded' else 'failed' end,
 result=case when p_error is null then p_result else null end,error=left(p_error,500),updated_at=now()
 where id=p_run_id and claim_token=p_token and status='running' and lease_expires_at>=now();
 get diagnostics n=row_count;return n=1;
end;
$$;
create function public.request_cancel(p_run_id uuid)
returns boolean language plpgsql security definer set search_path='' as $$
declare n int;
begin
 update public.runs r set status='cancelled',updated_at=now()
 where r.id=p_run_id and (r.requested_by=auth.uid() or public.has_project_role(r.project_id,array['admin']))
 and public.has_project_role(r.project_id) and r.status in ('queued','running');
 get diagnostics n=row_count;return n=1;
end;
$$;
revoke all on function public.claim_run(),public.heartbeat_run(uuid,uuid),public.complete_run(uuid,uuid,jsonb,text) from public,anon,authenticated;
grant execute on function public.claim_run(),public.heartbeat_run(uuid,uuid),public.complete_run(uuid,uuid,jsonb,text) to service_role;
revoke all on function public.request_cancel(uuid) from public,anon;
grant execute on function public.request_cancel(uuid) to authenticated;

-- Private artifacts skeleton; no public URLs or bucket-level read grants.
insert into storage.buckets(id,name,public) values('aurora-artifacts','aurora-artifacts',false) on conflict(id) do nothing;
create policy aurora_artifacts_read on storage.objects for select to authenticated
 using(bucket_id='aurora-artifacts' and exists(select 1 from public.project_members m
  where m.user_id=auth.uid() and m.project_id::text=(storage.foldername(name))[1]));
-- Upload/update is worker/admin provisioning only in this first skeleton.
