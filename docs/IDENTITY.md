# 제품 코드 대응·결합 감사 (U19)

생산기지 범위가 다른 같은 코드, 제품의 여러 별칭, 승인·시점·조인 중복을 점검하는 독립 도구입니다. 제품 ID와 패턴 부위명 ID는 별개입니다. 기존 감사와 모델·Supabase 권한을 유지하며, 별도 합성 주간 어댑터의 수요예측 연결·로컬 브라우저 검증/등록을 [추가했습니다](FORECAST_FILES.md). 기업 대응표 승인·ERP/동적 시점 연결·Supabase 저장은 후속입니다.

## 실행

코드 저장소 루트에서 Python 3.11 이상으로 실행합니다. 추가 패키지가 필요하지 않습니다. 출력은 **새 디렉터리**여야 합니다.

```sh
PYTHONPATH=src python3 -m aurora identity --input configs/examples/identity-valid.json --output results/identity-valid-1
PYTHONPATH=src python3 -m aurora identity --input configs/examples/identity-conflicts.json --output results/identity-conflicts-1
```

정상 종료 0, 계약/파일 오류 1, 격리 또는 대응표 중첩 발견 2입니다. 종료 2도 `mapped.json`, `quarantine.json`, `audit.json`, `report.md`, `artifacts.json`을 남깁니다. 전체 통과는 `ready_for_downstream: true`로만 판단합니다. 파일을 덮어쓰지 않습니다. 마지막 manifest가 없는 디렉터리는 완료 산출물로 취급하지 않습니다.

로컬 웹 수요예측 탭 하단의 **공통 선행 점검 · 제품 코드 대응과 데이터 결합**을 펼쳐 정상/반례를 선택합니다. `/api/identity-demo?case=valid|conflicts`는 허용된 합성 파일만 새로 계산합니다. Pages 화면은 `client/demo/identity/`의 저장된 합성 점검을 표시합니다. 로컬 계산 오류를 저장된 성공 결과로 바꾸지 않습니다. 이 기존 두 점검 경로는 선택한 예측 데이터셋과 독립적입니다. 별도 합성 ID→주간 파일 경로의 실제 계산/출처는 FORECAST_FILES.md를 따르며 기업 ERP/클라우드 연결로 표시하지 않습니다.

## 입력 계약

`aurora-product-identity-input-v1`, 최대 4 MiB, 대응 최대 2,000개·원천 1~10,000행. 알 수 없는 필드·중복 JSON 키·ID·비유한 수·잘못된 날짜는 거부합니다. 예시 파일의 전체 필드를 따르세요.

- 최상위: `schema_version`, `version`, `data_kind`(synthetic/public/mixed/company), `mapping_version`, `as_of`, `provenance`, `mappings`, `records`.
- 대응: `mapping_id`, `source_system`, `source_scope`, `source_code`, `canonical_product_id`, `valid_from`, `valid_to`, `known_at`, `approval_status`, `approved_by`, `evidence`.
- 원천: `row_id`, `record_key`, `record_type`, `source_system`, `source_scope`, `source_code`, `org_id`, `location_id`, `event_date`, `unit`, `quantity`.

`source_code`는 공백을 정리하거나 숫자로 바꾸지 않는 문자열입니다. `0012`와 `12`는 다릅니다. `source_system + source_scope`에는 코드가 유일한 법인/생산기지 범위를 명시합니다. `record_key`는 해당 범위·자료 종류에서 원천 업무 행을 식별해야 합니다. 같은 키는 중복으로 모두 격리합니다. BOM은 제품 ID만 연결하고 `record_key`가 패턴 버전·조각 행을 구별해야 합니다. 이 도구는 부위명 정답을 만들지 않습니다.

유효 기간은 **[valid_from, valid_to)**이며 null 종료는 무기한입니다. 해당 사건 날짜에 유효하고 `known_at <= as_of`인 승인 대응 하나만 사용합니다. `known_at`은 승인된 대응을 해당 의사결정에 이용할 수 있던 날짜로 기록해야 합니다. 후보/거절은 자동 승인하지 않습니다. 날짜 단위 계약이므로 같은 날 안의 순서는 검증하지 못합니다. 과거 예측을 재생할 때는 각 예측 원점의 as_of로 별도 감사해야 합니다. 현재 날짜의 대응표로 과거 전체를 감사한 결과는 과거 시점 검증을 대신하지 못합니다.

알려진 승인 유효기간의 중첩은 참조 행이 없어도 대응표 문제로 남깁니다. 단일 대응 적용 후 같은 제품/조직/위치/날짜/단위의 재고 스냅샷이 두 개면 모두 격리합니다. v1은 이 단위에서 하나의 완결 스냅샷을 가정합니다. 실제 창고가 독립 bin/lot 행을 제공하면 grain 계약을 먼저 확장해야 하며 조용히 합산하지 않습니다. 서로 다른 판매 거래는 유지합니다.

수량은 0 이상·1e12 이하의 유한 수이며 반품 보정은 별도 계약입니다. 자료 종류·조직·위치·날짜·단위별로 `원천 = 연결 + 격리` 행 수/수량을 검사합니다. 재고를 날짜 간 합산하지 않고 단위를 혼합하지 않습니다. 수량 합계는 Decimal 기반 문자열입니다. 원천/대응/코드 SHA-256과 행별 mapping_id를 보존합니다.

## 공개 데이터 수집·적용

공식 [WDC Products](https://webdatacommons.org/largescaleproductcorpus/wdc-products/index.html)의 80% corner-case multi-class·pair-wise ZIP을 받았습니다. 두 형식은 같은 벤치마크의 대안 표현이며 별개의 독립 표본으로 합치지 않습니다. 원본 ZIP은 프로젝트 `04_데이터/원본/공개연구데이터/WDC_Products/`에 보존합니다. 원본과 ID 파생 파일은 공개 저장소에 포함하지 않습니다. 배포 페이지가 무료 공개 다운로드를 제공하지만 데이터 전용 재배포 라이선스는 명확히 확인하지 못했습니다. 코드 저장소 라이선스를 원본 데이터에 적용하지 않습니다.

```sh
PYTHONPATH=src python3 tools/fetch_identity_wdc.py --output results/wdc-raw-new
PYTHONPATH=src python3 tools/prepare_identity_wdc.py --raw results/wdc-raw-new --output results/wdc-identity-new
```

다운로드는 고정 SHA-256·40 MiB 한도·ZIP CRC를 검사합니다. 가공 도구는 두 ZIP의 18개 JSON.gz를 파싱하고 split별 수·해시와 ID 교집합을 기록합니다. v1에서 선택한 `multi...train_small`은 **1,000 offer ID / 500 cluster ID**입니다. 제공 정답으로 대응표를 만들고 **거래·수량·조직·날짜·유효기간·known_at·승인 메타데이터는 합성**으로 추가했습니다(`data_kind=mixed`). 소스의 웹사이트별 원천 코드는 없으므로 가상의 생산기지 코드라고 표시하지 않습니다. 주어진 정답 연결을 다시 읽은 결과이며 매칭 모델을 학습·평가하지 않습니다.

정상 입력은 1,000행 전부 연결, 오류 주입 입력은 1,004행 중 996연결·8격리·대응표 중첩 1건이며 그룹별 수량은 보존됐습니다. 미매칭1·충돌1·미승인1·기준일 이후 대응1·중복 원천2·중복 재고2를 검출했습니다.

**데이터 확인 사항:** 내려받은 multi-class small/medium/large 설정에서 train↔valid·train↔기본 test ID 교집합은 각각 0이지만 valid↔기본 test는 각각 **4 ID**입니다. 원본을 수정하지 않았으며 `benchmark_evaluation_ready=false`로 기록합니다. 모델 비교 전 분할 정합성을 재확인하고 파생 분할 정책·제외량을 먼저 고정해야 합니다. 현재 도구는 train_small만 대응 점검에 사용하고 valid/test로 대응표를 만들거나 성능 수치를 산출하지 않습니다.

## 검증

```sh
PYTHONPATH=src python3 -m unittest tests.test_identity -v
# 실행 중인 로컬 서버와 Playwright/Chrome이 있을 때:
AURORA_TEST_URL=http://127.0.0.1:8765 node tests/test_identity_ui.mjs
```

11개 단위 검사는 범위/선행0/별칭·시점 경계·승인·중첩·미매칭·재고 grain·Decimal 수지·입력 거부·재현/해시·CLI 상태를 검사합니다. 브라우저 검사는 새 계산/저장 결과 구분, 격리·수량 표시, 탭·모바일, 로컬 오류 시 실패 유지까지 확인합니다. 기업 코드 승인·실제 거래 결합·통합 ERP 성과는 검증하지 않았습니다.
