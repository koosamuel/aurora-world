# Supabase 디지털 샘플링 실제 실행

U20 명세 검증/불변 등록과 U21 기하·CLIP/SD1.5 2D 생성이 공개 Pages → 실제 Auth → Supabase 큐 → Python 워커 → 비공개 Storage → 결과/서명 다운로드로 연결된다. 기존 forecast runs·SQL/RLS·로컬 DS 이력은 분리해 보존한다. U22 검토·U23 패턴/BOM·U24 효과 측정의 원격 저장은 이번 범위에 포함하지 않는다.

## 사용

1. 공개 사이트 둘째 탭에서 **서버 연결·로그인**을 누르고 기존 앱 Auth 계정으로 로그인한다. Supabase 대시보드의 GitHub 로그인과 앱 Auth 계정은 별개다. 디지털 샘플링 프로젝트의 runner/admin이 명세 검증/등록·새 생성·자신의 작업 취소를 할 수 있다. viewer는 명세/완료 결과만 읽는다.
2. 합성 제품/명세를 고른다. 수정본을 만들고 치수/조건을 변경해 **입력 검증**을 누르면 서버 검증 작업을 접수한다. Python의 기존 스키마·SVG/해시·단위·현행 기록 검사가 성공한 뒤 **검증 명세 등록**으로 불변 버전을 저장한다. 부모·동시 버전·원화 버전 충돌은 등록 RPC가 다시 검사한다.
3. **샘플 2개 생성·비교**에서 원하는 시드로 기하 GLB·정면/측면 SVG를 새로 만든다. **원화 해석·AI 이미지 2개 생성**은 기존 오프라인 CLIP·SD1.5로 새 2D PNG를 만든다. 기하는 학습 모델이 아니며 AI 이미지의 3D/치수·필수 조건/봉제 적합성을 보장하지 않는다.
4. 원격 실행 이력에서 상태·오류·완료 결과 재조회·대기/실행 취소를 확인한다. 탭을 다시 열면 로그인 후 같은 실행을 복원하거나 이력에서 선택한다. 완료 파일의 크기/SHA를 검사하고 다운로드한다.

계정 비밀번호/서비스 키는 코드·노트·Pages에 싣지 않는다. 사용자가 명시 승인한 기존 합성 실행 계정의 디지털 샘플링 역할만 viewer→runner로 변경했다. 새 계정은 만들지 않았으며 다른 프로젝트 권한은 유지했다. 실제 팀원은 담당자가 Auth/프로젝트 멤버십을 별도로 관리한다.

## 데이터·신뢰 경계

- 자체 합성6제품군의 기존12명세를 새 원격 레지스트리에 등록했다. 기업 자료는 받지 않는다. 기존 공개 ABO 변환/로컬 명세·검토/패턴·효과 기록은 원격으로 옮기지 않는다.
- 원문 명세 JSON512KiB를 문자열로 접수해 중복 키도 기존 Python 검증기에서 거부한다. 프런트엔드 파싱만으로 검증 완료를 만들지 않는다. 검증 결과의 등록은 워커가 성공시킨 같은 프로젝트/작업의 명세만 허용한다.
- `sampling_briefs`는 불변 명세/원화/요약/생성 출처를 보존한다. 버전/부모와 원화 변경 버전의 관계를 다시 검사한다. `sampling_runs`의 요청자·프로젝트·작업 종류·입력/시각은 변경할 수 없다.
- 요청은 같은 사용자/프로젝트/키로 재사용하고 입력이 다르면 거부한다. 프로젝트당 활성 작업4개·최대3시도, 120초 lease와 20초 heartbeat·claim token으로 만료/취소 시도의 늦은 완료를 막는다. 계산 자체가 즉시 중단되는 것은 아니며 취소된 시도의 파일은 게시/열람하지 않는다.
- 기하10파일, AI8파일을 `aurora-sampling` 비공개 버킷에 `project/sampling/run/attempt-N/SHA/name`으로 덮어쓰기 없이 올리고 모두 재다운로드·해시 검사한다. 완료 RPC는 결과/파일 목록·입력/시드·종류·수/이름·시도/경로·MIME·업로드 객체 존재를 검사한 뒤 한 트랜잭션으로 게시한다.
- RLS·Storage는 같은 프로젝트의 성공한 현재 시도만 읽게 한다. 익명 접근·브라우저 직접 쓰기·워커 RPC를 막는다. 서버 키는 `.env.local`의 워커 전용이며 클라이언트에는 기존 publishable key만 둔다. 120초 서명 URL은 메모리에서 사용하고 로그에 보존하지 않는다.
- 원격 오류가 나면 저장된 예제/로컬 계산으로 바꿔 성공 표시하지 않는다. 워커 상태는 온라인/AI 환경 여부만 공개하고 호스트 경로·키·모델 경로는 내보내지 않는다. 모델/입력/결과 해시는 기존 생성 보고에 보존한다.

## 코드·배포·운영

- SQL: `supabase/migrations/202610270002_sampling_execution.sql` (기존 core/public migration 뒤).
- 서버: `src/aurora/sampling_cloud.py`. 기존 sampling validator·geometry generate·AIService를 호출하며 로컬 DS 레지스트리/승인 이력을 수정하지 않는다.
- 클라이언트: `client/js/sampling-connection.js`와 U20/기하/AI 뷰, `app.js`의 같은 실제 Auth 어댑터. 로그인 상태 변경 시 이전 응답/출력을 무효화한다. PAT의 로컬 가상 역할을 원격 권한으로 사용하지 않는다.

```sh
# 개발 PC의 기존 보호된 환경/AI 설정을 사용한다.
PYTHONPATH=src python3 -m aurora.sampling_cloud --env-file .env.local --provision
PYTHONPATH=src python3 -m aurora.sampling_cloud --env-file .env.local
```

`--provision`은 기존12개 자체 합성 명세를 검증/등록하고 같은 버전의 다른 입력을 거부한다. 워커의 AI 설정은 기존 `.ai-local.json`과 캐시 모델이다. 새로운 외부 모델 다운로드/유료 생성 API가 필요하지 않다. `results/cloud-sampling/`에 시도별 출력·AI 로그를 보존하고 Git에서는 제외한다.

**계산 워커는 개발 PC 프로세스다.** Supabase DB/큐/Auth/비공개 저장과 Pages는 원격이지만, PC가 꺼지거나 잠들면 새 계산은 대기한다. 온라인 표시가60초 이상 갱신되지 않으면 오프라인으로 표시한다. 네트워크/PC 중단은 lease 만료 뒤 최대3시도로 복구하며 실패/대기/미측정을 성공으로 바꾸지 않는다. 상시 워커 호스팅은 후속 운영 항목이다.

## 검사·중단/복구

Python 단위 검사에 신규10개, 클라이언트 계약4개, PostgreSQL/RLS 신규60개를 추가했다. SQL의 Auth/Storage는 PGlite 대역이며 실제 서울 검증과 구분한다. 기존 수요예측 RPC/상태·결과 보존을 별도 대조했다.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run test:sql
node --test tests/test_labeling.mjs tests/test_datasets.mjs tests/test_public_client.mjs tests/test_sampling_client.mjs
# 실제 계정/서울 프로젝트의 수동 UI 검증. 비밀번호를 명령행 인자로 넣지 않는다.
AURORA_AUTH_FILE=/absolute/protected/auth.json AURORA_TEST_URL=https://koosamuel.github.io/aurora-world node tests/test_sampling_cloud_ui.mjs
```

인증/프로젝트 격리 실패, 입력/산출물 해시 불일치, 기존 DEM 회귀가 중단 기준이다. 복구 시 새 샘플 워커를 멈추고 Pages 클라이언트를 이전 커밋으로 배포해 저장 조회로 되돌린다. 새 테이블/비공개 파일·실행 증거는 보존한다. 이 단계에서 기업 IP·상시 운영·U22~U24 원격 승인/효과·AI3D/자동 봉제 패턴 완료를 주장하지 않는다.
