-- Apply after the migration in a NEW Aurora development project, not the bookstore.
insert into public.projects(id,name,project_type) values
 ('10000000-0000-4000-8000-000000000001','수요예측·운전자본','forecast'),
 ('10000000-0000-4000-8000-000000000002','패턴 부위명 자동 라벨링','labeling')
on conflict(id) do nothing;
insert into public.datasets(id,project_id,name,version,status,generator_config) values
 ('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001',
  '합성 주간 수요 · SKU 50 × 156주','synthetic-v1','ready',
  '{"seed":42,"skus":50,"weeks":156,"assumption_version":"demo-A01-A11-v1"}')
on conflict(id) do nothing;
-- Provision a user via Supabase Auth, then run as administrator with its actual UUID:
-- insert into public.project_members(project_id,user_id,role)
-- select id, '<AUTH_USER_UUID>'::uuid, 'admin' from public.projects;
-- Never grant project_members writes to the browser.
