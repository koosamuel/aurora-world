# 합성 주간 입력과 비공개 등록

이 경로는 `aurora-weekly-input-v1`의 합성 관측 총출하량만 지원합니다. ERP 원본·실제 회사 자료를 일반적으로 수입하는 기능은 아닙니다. M4/Quick Draw 원본·이미지·잠재 수요 파일을 업로드하지 않습니다.

## 파일 계약과 검증

- 단일 법인/창고, each/KRW, 1~100 SKU, 연속 ISO 월요일 20~520주, 파일 최대 4 MiB.
- 필수 최상위 필드: schema_version, synthetic=true, version, target=observed_gross_shipments, unit, currency, org_id, warehouse_id, periods, series, source.
- series의 각 항목: sku, pattern, values, statuses, stockouts, returns, unit_cost_krw. 전체 주간 배열 길이가 같아야 합니다. ID·주 중복, 주간 누락·역순, 단위/통화 혼합, 무한/NaN·음수·boolean 수량을 거부합니다.
- `observed` 수량은 0 이상, `missing`/`not_started`는 null입니다. 반품은 별도 양수/0으로 유지하며 missing의 반품은 null일 수 있습니다. 품절 플래그를 보존합니다.
- JSON 객체 중복 키·알 수 없는 필드도 거부합니다. 잠재 수요나 정답을 입력 필드로 전달할 수 없습니다. source는 생성기·원본 명세 SHA-256입니다.
- 연구 참고 변환기는 명세에 있는 품목/주간 관측 파일의 SHA-256을 먼저 대조하고, SKU/주 키·알 수 없는 SKU·법인/창고·품목 단위·총출하량 대응을 검사합니다. `evaluation_only/`는 읽지 않습니다.

```sh
PYTHONPATH=src python3 -m aurora.inputs --research-root '../04_데이터/가공/2026-10-26_가상데이터_v1' --output '../04_데이터/가공/2026-10-26_가상데이터_v1/forecast/weekly_input_v1.json' --result results/research_input_result.json
PYTHONPATH=src python3 -m aurora.inputs --input '../04_데이터/가공/2026-10-26_가상데이터_v1/forecast/weekly_input_v1.json' --result results/research_input_result.json
```

`inputs.run_input()`은 고정 생성기를 재실행하지 않고 검증한 관측을 `forecast.run_series()`와 기존 분류/모델/재고 실험에 전달합니다. 달력은 파일에 있는 기간에서 이어집니다. 입력 파일 해시·출처 해시·검증 코드 해시·품절 수를 결과에 기록합니다. 100 SKU는 15,600관측, missing 60, 미개시 1,440, 반품 발생 90, 품절 212관측입니다.

출하량은 품절로 검열된 값이며 잠재 수요를 의미하지 않습니다. 재고 계산은 계속 공통 가상 단가 1,000 KRW·기본 정책을 사용합니다. 입력의 품목별 단가를 적용한 실제 투자 평가로 표현하지 않습니다. 관측 출하량을 수요 대리로 쓰는 합성 시뮬레이션의 한계를 화면에도 표시합니다.

## 관리자/워커 CLI 등록

```sh
PYTHONPATH=src python3 -m aurora.registered --input '../04_데이터/가공/2026-10-26_가상데이터_v1/forecast/weekly_input_v1.json' --project 10000000-0000-4000-8000-000000000001 --env-file .env.local
PYTHONPATH=src python3 -m aurora worker --env-file .env.local
```

기존 서울 개발 프로젝트와 `aurora-artifacts` 비공개 버킷을 사용합니다. 초기 SQL의 데이터셋·워커·RLS 계약을 유지하며 추가 권한이나 SQL 마이그레이션이 필요하지 않습니다. 등록은 **워커 비밀 환경을 가진 관리자 CLI** 경로이며 브라우저 업로드 권한을 제공하지 않습니다.

1. 로컬 파일을 검증하고 결정적인 JSON 바이트/SHA-256을 만듭니다.
2. 실제 forecast 프로젝트를 확인해 `validating` 메타데이터를 등록합니다.
3. `<project UUID>/inputs/<SHA-256>.json`에 덮어쓰기 없이 업로드합니다.
4. 비공개 API에서 다시 내려받아 크기·SHA-256·스키마·품목/기간 수를 재검증한 뒤에만 ready로 바꿉니다. 실패는 rejected입니다. 같은 버전의 다른 파일을 거부하고 같은 파일의 재실행은 재사용합니다.
5. `generator_config.mode=weekly_file_v1`과 input의 bucket/path/sha256/bytes를 저장합니다. 기존 생성 설정과 별도 모드입니다. 워커는 실제 run의 프로젝트와 파일 경로를 대조하고 해시·계약을 다시 검사한 뒤 계산합니다. 임의 다운로드 URL을 허용하지 않습니다.

멤버는 기존 프로젝트별 Storage 읽기 정책으로 접근할 수 있습니다. 익명 읽기·runner 업로드/메타데이터 변경은 계속 차단됩니다. 파일 객체를 공개 URL로 전환하지 않습니다. 이 초기 합성 등록 경로는 기존 runs.result를 사용합니다. 공개 거래의 artifacts/서명 다운로드는 [후속 실서버 구현](FULLSTACK.md), 합성 로컬 브라우저 등록/5파일 산출물은 [파일 실행 계약](FORECAST_FILES.md)을 따릅니다. 정규 관측 테이블과 Supabase 멤버 브라우저 업로드는 후속입니다.

## 화면과 검증

Pages에서 기본 50 SKU/연구 참고 100 SKU의 고정 합성 결과를 선택할 수 있습니다. 로그인한 Supabase 모드에서는 접근 가능한 ready 데이터셋과 해당 데이터셋의 실행만 표시합니다. 미리보기는 입력 파일을 배포하지 않고 계산 결과의 공개 가능한 합성 스냅샷만 게시합니다.

Python 테스트는 입력 오류·null/0/반품 구분·재현/보류 미사용·등록 재사용/충돌·손상 시 ready 금지·프로젝트 경계를 검사합니다. JS 테스트는 선택 데이터셋에 따른 파일/실행/RPC 분리를 검사합니다. 실제 서버 검증은 `tests/smoke_registered.py`로 수동 실행하며 CI는 이 파일을 실행하지 않습니다. 검증은 새로운 합성 개발 프로젝트에만 한정합니다.

남은 항목: Supabase 멤버의 브라우저 업로드/역할별 등록, 실제 ERP 거래 키·중복 집계·단위/품절 보정, 품목별 기업 비용/재고 입력, 독립 궤적/기업 장기 검증, PAT 라벨 검수 서버 저장·정답 버전/재학습. 공개 거래 장기/민감도 평가는 FULLSTACK.md에, 합성 로컬 파일 선택/검증/등록은 아래 후속 계약에 구현했다.

## 후속 로컬 브라우저 등록

U05 로컬 합성 파일 선택/검증·해시 고정 등록/재사용·실행/취소·5파일 보고와 U19 보수적 ID 주간 연결을 [별도 계약](FORECAST_FILES.md)으로 구현했다. 기존 관리자 CLI/원격 입력 권한은 유지하며, Supabase 멤버 브라우저 업로드는 후속이다.
