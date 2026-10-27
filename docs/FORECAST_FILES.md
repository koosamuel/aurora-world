# 합성 파일 등록·ID 감사 연결·실행 산출물 (U05/U19/U15)

첫째 탭에서 자체 합성 파일을 선택해 검증→불변 등록→데이터셋 선택→기존 예측/세그먼트/재고 계산→보고 파일 다운로드를 실행한다. 기업 자료/ERP·Supabase 브라우저 업로드·실제 멤버 권한을 연결한 기능은 아니다. 기존 관리자 CLI/비공개 등록·공개 거래 실서버 경로와 분리된 **loopback 합성 구현**이다.

## 실행·입력

`PYTHONPATH=src python3 -m aurora serve --port 8765` 실행 후 “합성 파일에서 예측 실행까지”에서 가상 작성자 역할을 적용한다. 자체 합성 JSON4MiB 이하를 선택하거나 ID 연결 예제를 검사한다. 원문 JSON과 주간 입력을 서버에서 다시 검증하고 해시를 확인한 뒤 등록한다. ready 데이터셋만 새 실행 목록에 나타난다. 품목/기간은 파일에 고정되며 horizon·season_length·validation_origins만 실행 옵션으로 받는다. 선택한 데이터셋의 실행만 조회/취소한다.

역할은 누구나 선택하는 기존 U22 고정 합성 시뮬레이션이다. 서버는 작성자 세션을 검사하고 열람자/검토자/승인자의 등록·실행·취소를 거부하지만 실제 사용자 인증/멤버십은 아니다. 두 탭과 Supabase의 실제 로그인 상태와 구분한다. Pages는 새 업로드/실행 없이 저장된 자체 합성 예제를 조회한다.

입력은 두 가지다.

- `aurora-weekly-input-v1`: 기존 [주간 파일 계약](INPUTS.md). each/KRW·단일 법인/창고·20~520개 연속 월요일·1~100 SKU, 관측/결측/미개시·반품·품절을 구분한다. 원문 중복 JSON 키/비유한 수·미허용 필드를 거부한다.
- `aurora-identity-weekly-input-v1`: `version`, `periods`, `unit_costs_krw`, `coverage_assertion`, `identity`를 갖춘 자체 합성 묶음. `identity`는 기존 [U19 계약](IDENTITY.md)의 mappings/records다. 예제 파일 전체 필드를 따른다.

**등록 전 검증 취소**는 File 읽기/검증 요청을 중단하고 늦은 응답이 등록 버튼을 다시 켜지 못하게 한다. 아직 등록하지 않은 파일이다. 등록 POST를 보낸 뒤에는 서버 커밋이 완료될 수 있어 취소를 약속하지 않는다. 응답이 끊기면 데이터셋 목록 재조회·같은 파일 재시도로 ready/재사용 여부를 확인한다. 원문/변환 해시가 검증 결과와 달라지면 등록을 거부한다. 같은 버전·같은 변환 입력은 재사용하고, 다른 입력으로 덮어쓰지 않는다. 재사용 시 처음 저장한 원문과 출처를 보존한다. 보관/검증 실패는 rejected로 남고 실행할 수 없다.

## U19의 보수적 주간 입력 연결

기존 감사 도구를 유지하고 `identity_weekly.py` 어댑터를 별도로 만들었다. 합성 `observed_sales` 흐름을 **합성 관측 총출하**로 선언한 경우만 사용한다. 기존 ID 계약의 자료 종류 토큰을 실제 매출=출하라는 기업 가정으로 확대하지 않는다.

1. 모든 원천/대응을 기존 `identity.audit()`로 검사한다. 격리·대응표 중첩이 하나라도 있으면 전체 실행 입력 연결을 거부한다. 일부 통과분을 성공 파일로 바꾸지 않는다.
2. 감사의 as_of는 원천 관측 마지막 날짜까지 허용하지만 **모든 대응의 known_at이 최초 관측 주 이전/당일**이어야 한다. 미래 검증/보류 구간에서 배운 대응표로 과거 입력을 정리하지 못하게 하는 보수적 계약이다. 동적으로 새 대응이 생기는 기업 이력은 지원하지 않는다.
3. each·단일 법인/창고의 관측 흐름만 연결한다. 재고 스냅샷/BOM·다른 단위·공개/혼합/기업 자료는 이 합성 어댑터에서 거부한다.
4. 합성 선언 `synthetic_complete_weekly_shipments_no_stockouts_or_returns`와 SKU×주 전체에 실제 원천 행이 필요하다. 빈 주를0으로 채우지 않는다. 관측0은 원천0행으로 보존한다. 품절/반품이 있는 입력은 ID 어댑터에서 추정하지 말고 일반 주간 파일의 명시 상태 계약을 사용한다.
5. 별칭의 **서로 다른 업무 거래**를 Decimal로 합산하고 제품/주별 원천 row_id·mapping_id·수량, 원천=연결+격리 수지·입력/대응/엔진 SHA를 보존한다. float로 변환할 때 직렬 수량 정밀도가 달라지면 거부한다. 실제 회사 거래의 중복 원천/단위/재고 grain 확인을 대체하지 않는다.

감사 결과를 보고서 출처에 연결하며 실제 매칭 모델을 학습하거나 기업 승인 대응표를 만든 것은 아니다. 선행0 코드·원문 코드는 보존한다. 매핑 버전/원천이 바뀌면 주간 파일 체크섬도 바뀌고 새 버전 등록이 필요하다.

## 저장·큐·산출물

`forecast_files.py`는 별도 SQLite의 불변 파일 메타데이터와 내용 해시 경로에 원문/변환 파일을 저장한다. 매 실행에 두 파일의 크기/SHA·스키마를 다시 확인한다. 기존 `inputs.run_input()`을 호출하며 생성기를 다시 실행하지 않는다. 기존 6후보·시간순 선택/최종 평가·경험 구간·공통 가상 단가1,000원 재고 정책을 유지한다. 입력 단가 메타데이터를 실제 SKU별 정책에 적용한 것으로 표시하지 않는다. 독립 확률 보정(U07)과 기업 품절 보정/기존 방식 대조는 후속이다.

작업은 queued→running→succeeded/failed/cancelled, 같은 요청 키/다른 입력 충돌·데이터셋별 이력 분리·attempt/lease fencing·최대3시도 복구를 사용한다. 주기 워커가 재시도하며 취소/만료된 시도의 늦은 완료를 거부한다. 완료한 현재 시도의 파일만 공개한다. 계산/파일 작성 실패를 성공으로 바꾸지 않는다.

- `result.json`: 파일 목록을 붙이기 전의 불변 전체 예측/확장 결과.
- `predictions.csv`: 공통 계산부의 SKU/분할/원점/horizon/모델/실제/예측/척도.
- `inventory.csv`: SKU·예측/정책별 서비스·보유/미입고·가정 기반 투자액.
- `report.md`: 기존 세그먼트/예측/재고 보고에 등록/ID 출처와 적용 한계를 추가.
- `input-lineage.json`: 원문→감사/주간 집계→실행/설정·attempt의 추적.
- `manifest.json`: 위5파일의 크기/SHA와 입력/실행/시도.

보고 파일은 다운로드 때 해시를 다시 확인한다. CSV는 UTF-8 BOM/LF이며 문자열의 수식 시작 문자를 이스케이프한다. 원본 결과 JSON과 화면의 계산값은 같고, 화면 결과에는 다운로드 메타데이터가 추가된다.

| API | 기능 |
|---|---|
| POST `/api/forecast-files/validate` | 원문 JSON, 합성 작성자 세션; 저장 없이 검증/원문·변환 해시 반환 |
| POST `/api/forecast-files/datasets` | 같은 원문, `X-Weekly-SHA256`/`X-Upload-SHA256`; 불변 등록/재사용 |
| GET `/api/forecast-files/datasets` | ready/rejected 상태·검증 메타데이터 |
| GET `/api/datasets` | 기존 생성/공개 거래와 ready 파일 데이터셋 선택 목록 |
| POST `/api/forecast-files/runs` | `{project_type,dataset_id,request_key,config}`, 합성 작성자 |
| GET `/api/forecast-files/runs[/{run_id}]?dataset_id=...` | 단일 데이터셋 이력/결과; 다른 데이터셋의 실행은404 |
| POST `/api/forecast-files/runs/{run_id}/cancel` | `{dataset_id}`, 합성 작성자; 대기/실행 취소 |
| GET `/api/forecast-files/artifacts/{run_id}/{name}` | 성공한 현재 시도·허용 파일명·크기/SHA 확인 후 제공 |

기존 Host/Origin loopback 제한을 유지한다. 입력400·역할403·검증/버전/요청 키 충돌409, 없는/다른 자료의 실행·미완료 파일404다. `results/forecast-files.sqlite3`, `forecast-file-inputs/`, `forecast-file-artifacts/`는 Git 제외다. 기존 DEM Supabase SQL/RLS/권한·Storage·원격 워커를 변경하지 않았다. Supabase 브라우저 업로드/사용자별 멤버 권한·기업 대응표 등록은 후속이다.

## 합성 데모·재현

자체 합성12대응·960출하 행(2별칭×6 SKU×80주)을 감사해480 SKU/주 입력으로 연결했다. 생성 정답 매핑과 승인 메타데이터도 합성이며 매칭 정확도/기업 승인 실적이 아니다. 원문·변환·검증·저장 결과와5파일/manifest, 총11파일을 공개한다. 새 외부 자료/모델 다운로드나 새 학습은 필요하지 않다. 기존 AI 회귀는 별도로 확인한다.

```sh
PYTHONPATH=src python3 tools/build_forecast_file_demo.py --output results/new-file-demo
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_forecast_files.py' -v
```

새 출력 폴더를 사용한다. 같은 입력/설정의 수량·평가/재고 계산은 재현되며 등록 시각·실행 ID·세션 등 접수 메타데이터는 실행마다 다르다. Pages의 예제는 이 실제 계산의 저장 결과이며 새 계산이라고 표시하지 않는다.
