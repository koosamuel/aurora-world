# 공개 거래 자료의 클라이언트·서버 연결

2026-10-27 기준: 다운로드한 UCI Online Retail II를 웹의 데이터셋 선택 → 실행 요청 → Python 계산 → 요약 조회 → 파일 다운로드에 연결했다. 로컬 실제 계산과 정적 미리보기는 검증했다. **서울 Supabase의 새 마이그레이션은 자동 승인 검토에서 차단되어 아직 실행하지 않았다.** 원격 공개자료 등록·새 워커 실행·인증 다운로드의 실서비스 검증은 구체적 SQL 실행에 대한 사용자 승인 후 진행한다. 기존 합성 원격 실행 경로는 유지한다.

## 바로 확인

이 README가 있는 코드 폴더에서 실행한다. 프로젝트의 기본 위치에서는 준비된 `../04_데이터/가공/2026-10-26_UCI_Online_Retail_II/weekly.json`을 자동으로 찾는다. 별도 위치는 아래처럼 지정한다.

```sh
PYTHONPATH=src python3 -m aurora serve --port 8877 --public-input '../04_데이터/가공/2026-10-26_UCI_Online_Retail_II/weekly.json'
```

`http://127.0.0.1:8877/#/forecast`에서 **UCI 공개 거래**를 선택하고 실행한다. 정책 JSON은 선택 입력이며 예시는 [공개 거래 설명](PUBLIC_RETAIL.md)의 품목별 정책/비용 계약을 따른다. `{}`는 미확보 비용을 null로 유지한다. 68주 선택·4주 워밍업·32주 평가·1주 rolling 분할은 고정이며 합성의 예측기간 설정을 적용하지 않는다. 합성 데이터로 돌아가면 기존 설정과 화면을 사용한다. loopback 로컬 모드는 인증 없는 개발용이다.

Pages에서는 **공개 거래 저장 결과**를 선택해 미리 계산한 요약과 예측/재고 CSV·보고서 3개를 본다. 브라우저에서 새 Python 계산을 실행한 것으로 표시하지 않는다. 고객 ID·invoice ID·상품 설명·원본 Excel은 게시하지 않는다. CC BY 4.0 출처와 가공 사실은 요약·보고서에 표시한다. Naive MAE 178.269보다 선택 182.500이 나쁜 결과를 그대로 보존한다.

## 서버 적용 절차 — 승인 전에는 실행하지 않음

대상은 기존 `ai-applications / aurora-world`, South Korea/Seoul, ref `unajjkuccpqggulpqhmo`이다.

1. [202610270001_public_execution.sql](../supabase/migrations/202610270001_public_execution.sql)을 SQL Editor에서 `begin;` / `commit;`으로 감싸 한 번 적용한다. 기존 합성 전용 제약을 dataset_kind 제약으로 교체하고, 산출물/다운로드 요청 기록 테이블·RPC를 추가하며 Storage 읽기 정책을 현재 성공한 실행의 산출물로 제한한다. 기존 프로젝트 입력 읽기는 유지하고 브라우저 쓰기 권한은 추가하지 않는다. 버킷은 JSON/CSV/Markdown 및 파일당 48 MiB로 설정한다. 데이터 행 삭제는 없으며 실패 시 트랜잭션 전체를 롤백한다. 재적용용 SQL은 아니므로 성공 후 다시 실행하지 않는다.
2. 마이그레이션 승인·적용 후 기존 forecast 프로젝트 UUID로 공개 주간 파일을 등록한다. 서비스 키는 기존 보호 환경 파일에서만 읽으며 Git이나 브라우저에 넣지 않는다.

```sh
PYTHONPATH=src python3 -m aurora.public_service --input '../04_데이터/가공/2026-10-26_UCI_Online_Retail_II/weekly.json' --project '<기존 forecast 프로젝트 UUID>' --env-file .env.local
PYTHONPATH=src python3 -m aurora worker --env-file .env.local
```

3. 배포 화면에서 Supabase 로그인 → UCI 공개 거래 → 정책 입력 → 실행 → 워커 완료 → 5개 파일 다운로드를 검증한다. 익명/비멤버/다른 프로젝트/만료 시도 접근 거부, 기존 합성 실행도 확인한다. 새 dataset_kind 컬럼이 없는 서버에서는 클라이언트가 기존 합성 조회로 되돌아가므로 클라이언트 배포가 DB 변경을 강제하지 않는다.

## 저장·권한·재현 경계

- 입력은 검증 → `validating` → 비공개 Storage → 읽기/크기/해시 검증 → `ready` 순서다. 같은 버전의 다른 내용은 덮어쓰지 않는다.
- `runs.result`에는 약 17 KB 요약을 저장하고 상세 `result.json`, `forecast.csv`, `inventory.csv`, `decisions.csv`, `report.md`는 비공개 Storage에 둔다. 전체 결과 약 34 MB를 브라우저 DOM/JSONB로 전달하지 않는다.
- 경로는 프로젝트/실행/attempt/해시/파일명에 묶는다. 서비스 전용 완료 RPC가 유효 claim token·lease·실제 Storage 객체·5개 메타데이터를 확인하고 산출물 등록과 성공 상태를 함께 확정한다. 만료 시도의 파일은 읽기 정책에서 공개되지 않는다. 미완료 파일 청소는 후속 운영 항목이다.
- 다운로드 요청 RPC가 멤버십과 성공한 현재 시도를 확인해 요청 기록을 남기고, 클라이언트가 120초 서명 링크를 요청한다. 같은 서버의 허용 경로와 바이트 수·SHA-256을 확인해 저장한다. 요청 기록은 실제 파일 전송 완료의 증명이 아니다.
- 로컬 공개 큐도 별도 SQLite와 실행별 파일을 사용하며 완료한 실행의 허용 파일만 크기/해시 확인 후 제공한다.
- 원본 판매는 잠재 수요가 아니며 재고는 조건부 시나리오다. 실제 재고·조달원가·품절이 없어 기본 금액은 null이다. 임의 비용 입력은 출처 있는 기업 값과 구분한다. 자세한 집계/분할/정책 한계는 [PUBLIC_RETAIL.md](PUBLIC_RETAIL.md)를 따른다.

## 검증과 남은 범위

Python 45개, JS 9개, PGlite SQL/RLS 45개를 통과했다. SQL 검사는 Auth/Storage 최소 스키마 대역이며 Supabase 호스팅 검증을 대체하지 않는다. Playwright의 기존 로컬·미리보기/인증 대역·신규 공개 거래 3개 흐름에서 실제 계산·시나리오 필터·파일 해시·잘못된 정책·모바일 넘침을 확인했다.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --test tests/test_labeling.mjs tests/test_datasets.mjs tests/test_public_client.mjs
npm run test:sql
# 로컬 서버 실행 후 Playwright/Chrome 경로는 필요할 때 환경 변수로 지정
AURORA_TEST_URL=http://127.0.0.1:8877 node tests/test_public_ui.mjs
```

U06은 산출물·서명 다운로드 코드만 추가했고 정규 관측/예측 테이블은 후속이다. U09/U10/U15는 공개자료 로컬 웹·서버 코드까지 보강했으나 원격 적용 승인·실서비스 검증이 남았다. U05 브라우저 업로드, U07 독립 확률 보정, U11/U13 승인 마스터·Supabase 검수 저장, U14 재학습, 상시 워커 및 기업 성과 검증은 미완료다.
