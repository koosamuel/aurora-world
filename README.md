# Aurora World

오로라월드 과제용 코드. 저장소 주소: https://github.com/koosamuel/aurora-world

한 화면에서 **수요예측·운전자본**과 **디지털 샘플링·라벨링** 탭을 구분합니다. 합성 기준선·수요 세그먼트·모델 선택·재고 비교와 패턴 라벨링·검수 데모가 동작합니다. 기업 입력과 운영 재학습은 후속입니다. 프로젝트 목표·전체 진행 기준은 상위 `00_프로젝트_목차.md`, 상세 후속 설계는 `01_기획_회의/04_구현계획.md`에서 관리합니다.


- 배포 화면: https://koosamuel.github.io/aurora-world/
- 가상 이미지·데이터 미리보기: https://koosamuel.github.io/aurora-world/demo-data.html
- Supabase 서버: https://supabase.com/dashboard/project/unajjkuccpqggulpqhmo (ai-applications / South Korea, Seoul / ap-northeast-2)
- 서버 SQL 코드: https://github.com/koosamuel/aurora-world/tree/main/supabase

GitHub 저장소는 공개이며 Pages 게시·고정 합성 데모·실제 Supabase Auth→실행→로컬 워커→결과 표시를 확인했습니다. 데이터·Auth·RPC는 Supabase에, Python 워커는 개발 PC에 있습니다. 실제 팀원용 Auth 사용자·멤버십 등록과 상시 워커 호스팅은 후속 운영 설정입니다.

## 로컬에서 바로 실행

Python 3.11 이상, Python 추가 의존성 없이 실행합니다. 아래 명령은 이 README가 있는 코드 폴더에서 실행합니다.

```sh
PYTHONPATH=src python3 -m aurora serve --port 8765
```

http://127.0.0.1:8765 에서 `합성 기준선 실행`을 누릅니다. Python이 합성 데이터를 생성하고 SQLite 작업 큐를 통해 계산·저장한 결과를 화면에 표시합니다. 프로젝트 기본 위치에서 UCI 가공 입력이 있으면 공개 거래 데이터셋도 선택할 수 있습니다([클라이언트·서버 연결](docs/FULLSTACK.md)). 이 모드는 로컬 개발용이며 계정 인증은 없습니다. 서버는 loopback 주소에만 바인딩합니다. 중단은 Ctrl+C입니다.

```sh
PYTHONPATH=src python3 -m aurora demo --config configs/demo.json --output results/baseline.json
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

기본 설정은 seed 42, 50 SKU, 주별 156주, 예측 4주, 계절 주기 52주입니다. 마지막 4주는 최종 평가용, 그 이전에 4주씩 3개 원점을 검증합니다. 모든 원점에서 그 이전 이력만 사용합니다. 차트의 다음 4주 예측은 전체 관측 이력으로 별도 계산하며 평가 점수와 구간이 다릅니다.

Naive·계절 naive의 공통 예측 가능 대상 MAE·편향·MASE를 표시합니다. 모델별 전체 범위 지표도 JSON에 남깁니다. MASE 분모는 학습 이력의 계절 차이 평균이며 양수인 경우만 보고합니다. 상수·전기간 0·짧은 이력·누락·반품 사례를 포함하고, 미관측·반품을 수요 0으로 대체하지 않습니다. 같은 데이터/설정은 같은 결과를 재현합니다. 기업 기존 방식과의 개선이나 운전자본 절감 실적은 아직 평가하지 않았습니다.

## 디지털 샘플링 U20

두 번째 탭에서 합성 원화·치수/원단/색상 조건·현행 측정 입력을 확인하고, 로컬에서 명세 수정본 검증·불변 버전 등록을 실행할 수 있습니다. 6제품/12버전을 제공합니다. Pages는 저장된 합성 명세만 표시합니다. [U20 계약·실행·출처·후속 범위](docs/SAMPLING.md)를 확인하세요.

## 제품 ID 대응·결합 감사

별도 합성 예제의 승인·시점·기지별 코드·별칭·미매칭·중복을 로컬 CLI/웹에서 점검할 수 있습니다. 무료 공개 WDC Products도 다운로드해 ID 연결 점검에 적용했습니다. 저장된 Pages 결과·혼합 데이터·분할 중복 확인 사항과 실행 방법은 [U19 안내](docs/IDENTITY.md)에 기록합니다. 기존 예측/라벨링 입력과 Supabase 스키마는 유지합니다.

## Supabase 연결 골격

새 Aurora 개발 프로젝트에서 아래 순서로 설정합니다. 기존 어린이 작가 프로젝트는 변경하지 않습니다.

1. SQL Editor에서 `supabase/migrations/202610260001_core.sql`을 적용한 뒤 `supabase/seed.sql`을 실행합니다. 새 프로젝트 전용 초기 마이그레이션이므로 한 번만 적용합니다.
2. Supabase Auth에서 사용자를 생성하고, seed 주석의 SQL로 해당 UUID를 프로젝트 멤버로 등록합니다. `viewer`는 조회, `runner`/`admin`은 실행 요청이 가능합니다. 브라우저는 멤버십을 변경할 수 없습니다.
3. 화면의 `연결 설정`에 프로젝트 URL과 publishable 또는 legacy anon 공개 키를 입력하고 로그인합니다. `client/config.js`에는 서울 개발 프로젝트 URL·publishable 공개 키가 설정돼 있습니다. 기본 화면은 합성 데모이며 `연결 설정`에서 모드를 바꿉니다. 세션 토큰은 브라우저 메모리에만 보관하므로 새로고침 뒤 다시 로그인합니다. 서버가 반환하는 접근 가능 프로젝트만 조회합니다.
4. 워커용 환경에 `SUPABASE_URL`과 **legacy service_role JWT**를 `SUPABASE_SERVICE_ROLE_KEY`로 설정하고 아래 명령을 실행합니다. 이 초기 워커는 legacy JWT 인증 경로를 사용합니다. `.env.example`은 설명용이며 자동 로드하지 않습니다.

```sh
PYTHONPATH=src python3 -m aurora worker
# 한 작업만 처리하려면:
PYTHONPATH=src python3 -m aurora worker --once
```

워커가 없으면 요청은 `queued`에 머뭅니다. 워커는 원자적 선점·120초 lease·30초 heartbeat·시도별 토큰을 사용합니다. 만료 작업은 최대 3회 선점하며, 취소되거나 만료된 시도의 완료는 반영하지 않습니다. 요청의 동일 키 재전송은 같은 실행을 반환하고 다른 설정 재사용은 거부합니다. 워커 프로세스가 연결 오류로 종료되면 다시 시작해야 합니다.

초기 DB는 `projects`, `project_members`, `datasets`, `runs`와 RPC/RLS를 구현합니다. 합성 입력은 고정 생성 설정으로 등록하고, 결과는 `runs.result`의 버전 있는 JSONB로 저장합니다. 정규 관측·예측·재고·라벨 테이블과 브라우저 업로드는 후속 단계입니다. 공개 거래 산출물 다운로드와 새 SQL의 서울 원격 적용·실서비스 검증을 완료했습니다([적용 절차](docs/FULLSTACK.md)). 합성 입력의 관리자 CLI 비공개 업로드/읽기는 구현했습니다. `aurora-artifacts` 버킷은 비공개이며 멤버십과 현재 성공한 실행에 맞춘 읽기 정책을 적용했습니다. 서울 개발 프로젝트에서 실제 Auth 로그인/로그아웃·멤버 조회·접수/워커/결과·익명 차단·브라우저의 워커 RPC 거부를 검증했습니다. 합성 입력 Storage 업로드·읽기·해시 검증은 실제 서버에서 확인했으며 브라우저 업로드는 후속이며 공개 거래 산출물의 원격 마이그레이션·인증/서명 다운로드를 검증했습니다.

서비스 키는 워커 환경에서만 사용합니다. `.env`, 결과 DB, 기업 원본, 교재·논문은 Git에 포함하지 않습니다. 클라이언트 설정 폼은 secret/service_role 키를 거부합니다. GitHub Pages에 배포하는 합성 예제 외의 실제 결과는 인증 후 Supabase에서 조회하도록 설계했습니다.

## 정적 미리보기와 GitHub Pages

일반 정적 서버나 Pages에서는 Python을 실행할 수 없습니다. 이때 `합성 데모 불러오기`는 `client/demo/baseline.json`의 **미리 계산한 고정 합성 결과**만 표시합니다. 새 계산으로 표현하지 않습니다. 스냅샷 재생성:

```sh
PYTHONPATH=src python3 -m aurora demo --output client/demo/baseline.json
```

`.github/workflows/pages.yml`은 수동 실행용입니다. GitHub 저장소의 Pages source를 GitHub Actions로 지정한 후 실행하며 `client/`만 게시합니다. Supabase 개발 프로젝트와 초기 SQL 적용·실제 연결 검증을 완료했습니다. GitHub 공개 전환과 Pages 게시·실제 화면 검증을 완료했으며 확정 주소와 검사 근거는 프로젝트 구현 노트에 기록했습니다.

## 검증

Python 단위 테스트 45개(기존 28+공개 거래/재고 12+연결 5), JS 9개: 손계산 예측, 미래 누수 방지, 재현성·동일 대상 평가, 입력·누락·0분모 처리, 중복 요청·동시 선점·만료·취소·재시도 한도·실제 계산 저장.

```sh
npm ci --ignore-scripts
npm run test:sql
```

PGlite PostgreSQL에서 실제 마이그레이션/seed와 45개 권한·RPC 검사를 실행합니다. Auth/Storage 스키마는 테스트 대역입니다. 실서비스 Auth, 네트워크, Supabase 호스팅 환경의 검증을 대신하지 않습니다.

`tests/test_ui.mjs`는 Playwright로 실제 로컬 계산, 탭·새로고침/선택 복원, 모바일 가로 넘침, 비밀 키 거부를 검사합니다. 별도로 설치된 Playwright와 Chrome을 사용하거나, 환경 변수 `PLAYWRIGHT_MODULE`, `CHROME_PATH`를 지정할 수 있습니다. 테스트 전에 로컬 서버를 시작합니다. `tests/test_modes.mjs`는 정적 미리보기와 Supabase REST/Auth 대역을 검사합니다.

## 코드 위치

- `client/`: 두 탭·Auth/REST 어댑터·결과/차트
- `src/aurora/forecast.py`: 합성 생성·기준선·시간순 평가
- `src/aurora/jobs.py`, `server.py`: 로컬 큐·HTTP 데모
- `src/aurora/cloud.py`: Supabase 배치 워커
- `configs/demo.json`: 예측 가정 A01~A07·A10의 초기 설정 (A08~A09의 버전 있는 재고 가정은 `decisions.py`의 SETTINGS와 결과 JSON에 기록)
- `supabase/`: 초기 SQL·멤버십 등록 예시
- `tests/`: 계산·작업·PostgreSQL/RLS·브라우저 검증
- `results/`: 로컬 실행 데이터 (Git 제외)

## 공개 연구 자료와 확장 가상 데이터

원본·논문과 전체 가공 이미지는 코드 폴더 밖 프로젝트 자료 공간에서 관리합니다.

- 원본: `../04_데이터/원본/공개연구데이터/` — M4 Weekly Train/Test 359계열, 전체 메타데이터, Quick Draw 900개 표본, 공개 논문 2편.
- 가공: `../04_데이터/가공/2026-10-26_가상데이터_v1/` — 100 SKU×156주, 수요/재고 각 15,600행·발주 11,372행, 1,200개 패턴의 SVG/PNG/부위 정답/별칭/BOM, 아트워크 SVG/PNG 각각 100개.
- 화면: `client/demo-data.html` — 소수의 출처 표시 파생 이미지·집계만 게시합니다. `client/demo/gallery/summary.json`에 실제 확장 자료의 기준선 평가도 담았습니다.

이 확장 자료는 초기 실행 데모의 50 SKU와 별도 버전입니다. 현재 Supabase 워커는 초기 50 SKU 생성 계약과 등록 파일 입력 계약을 모두 처리하며, 연구 참고 100 SKU 수요도 엄격한 입력 검증·비공개 Storage·실제 워커 계산에 연결했습니다. 패턴 1,200개는 아래 라벨링 데모에 연결했습니다.

```sh
# 데이터 생성 시에만 Pillow가 추가로 필요합니다.
python3 -m pip install -e '.[data]'
PYTHONPATH=src python3 -m aurora.download_research --root ..
PYTHONPATH=src python3 -m aurora.prepare_data --raw '../04_데이터/원본/공개연구데이터' --output '../04_데이터/가공/새_버전'
PYTHONPATH=src python3 -m aurora.validate_data '../04_데이터/가공/새_버전'
PYTHONPATH=src python3 -m aurora.evaluate_dataset '../04_데이터/가공/새_버전' --output results/research_dataset_baseline.json
# 기본 자료 폴더 구조에서 갤러리 재생성:
python3 tools/build_gallery.py --root ..
# 보호 환경 파일로 실제 워커 실행:
PYTHONPATH=src python3 -m aurora worker --env-file .env.local
```

데이터 생성은 M4 Train의 과거 prefix에만 의존하며 M4 Test는 보관만 합니다. 누락·반품·품절·짧은 이력 등을 넣고, 잠재 수요는 평가 전용으로 분리합니다. 패턴 분할은 디자인 가족군 70/15/15이고 아트워크 원본도 split을 넘지 않습니다. 좌우/앞뒤가 같은 형상은 검수가 필요합니다. 검사 통과가 기업 일반화 성능·실제 원가·재단 가능성을 보증하지 않습니다.

연구 연결은 `docs/RESEARCH.md`를 참고합니다. 서비스 비밀 키와 테스트 계정 자격증명은 `.env.local`/`results/`에만 보관하고 Git 제외를 확인했습니다. `tests/smoke_supabase.py`는 새 합성 개발 프로젝트에 한해 수동으로 실행하는 실서비스 검증이며 CI에서 실행하지 않습니다. 대시보드 계정과 앱의 Supabase Auth 계정은 별도이므로 실제 팀원은 Auth 사용자와 멤버십을 등록해야 합니다.

## 합성 라벨링 데모

[라벨링 화면](https://koosamuel.github.io/aurora-world/#/labeling)에서 실행→디자인 선택→명칭 후보/형상 예측→표준명 확정·보류→생성 정답 비교→JSON 다운로드를 사용할 수 있습니다. 로그인 없이 브라우저에서 실제 kNN 계산을 수행합니다. 검수는 현재 브라우저 세션에만 저장합니다. 실제 업로드·Supabase 검수 저장·운영 재학습은 후속입니다.

형상은 7개 부위군까지 분류하고 12개 세부 부위의 좌우·앞뒤는 수동 검수합니다. 학습/검증/평가 840/180/180조각은 디자인 가족군으로 분리했습니다. 검증 macro-F1 0.990, 보류 1.000은 단순 합성 템플릿 성능이며 기업 정확도가 아닙니다. 정답은 별도 `truth.json`에서 비교 시 읽고 예측 입력으로 사용하지 않습니다.

```sh
PYTHONPATH=src python3 -m aurora.labeling '../04_데이터/가공/2026-10-26_가상데이터_v1' --output client/demo/labeling
node --test tests/test_labeling.mjs
```

`label-model.js`는 명칭 후보와 4개 기하 특성의 5-nearest neighbors 추론을 분리합니다. 브라우저 추론과 Python 평가의 일치·가족군 분리·수동 승인을 검사합니다. 공개 배포에는 자체 생성 윤곽·학습 특성/부위군·합성 정답을 포함하며 회사 자료·Quick Draw 원본은 포함하지 않습니다.

## 세그먼트·모델 선택·재고 비교

새 예측 실행에는 `decisions` 확장이 함께 저장됩니다. ADI/CV²와 분류 변경, 6개 후보·검증 선택/임시 세그먼트 규칙의 동일 대상 평가, 경험 구간, Naive/선택×버퍼 유무의 재고·서비스 비교를 화면에서 확인합니다. Pages는 이 확장을 담은 고정 합성 스냅샷이며 로컬/Supabase 워커는 새 실행마다 계산합니다. 기존 실행에 확장이 없으면 새로 실행하세요.

```sh
PYTHONPATH=src python3 -m aurora demo --output results/baseline.json --report results/decision_report.md
```

기본 공통 보류 146관측에서 검증 선택 MAE 1.663, Naive 2.192입니다. 버퍼 없는 재고정책은 95% 충족률에 미달하며 투자액 감소를 성공으로 판정하지 않습니다. 조건부 차이는 두 방식 모두 SKU별 서비스 목표를 충족하는 경우만 집계합니다. 평가 4주·소수 검증 오차의 합성 예시이며 기업 절감액을 뜻하지 않습니다. [방법·초기화·누락 처리·사건 순서·제외/한계](docs/DECISIONS.md).

## 합성 파일 입력과 100 SKU 서버 연결

`aurora-weekly-input-v1` 검증기가 중복 SKU/주·기간·단위·통화·수량·결측 상태를 검사합니다. 준비한 100 SKU/15,600관측을 비공개 Storage에 등록하고 워커가 해시 검증 후 실제 계산하도록 연결했습니다. 관리자 CLI 등록이며 브라우저 업로드는 후속입니다. 기존 DB/Storage 읽기 권한을 유지합니다.

Pages의 데이터셋 선택에서 기본 50 SKU와 연구 참고 100 SKU의 저장 결과를 비교할 수 있습니다. Supabase 모드에서는 접근 가능한 ready 데이터셋을 선택해 새 계산을 요청하고 해당 자료의 실행 이력을 조회합니다. 100 SKU는 품절로 검열된 관측 출하량이며 잠재 수요·실제 회사 수요가 아닙니다. [파일 계약·등록·재현·남은 범위](docs/INPUTS.md).

## 공개 실측 거래와 장기 평가

UCI Online Retail II의 1,067,371행을 취득해 104주·상위 100 SKU의 주간 입력을 만들고 기존 6개 예측 후보에 적용했습니다. 앞 68주로 품목/모델을 정하고 4주 워밍업 뒤 32주를 순차 평가합니다. 장기 재고 grid·품목별 정책/비용 계약·의사결정 CSV·파일 해시 보고를 추가했습니다. [취득·집계·실행·실제 결과와 한계](docs/PUBLIC_RETAIL.md). Excel 변환만 선택 의존성 openpyxl이 필요합니다.

공개자료 데이터셋 선택·서버 실행·요약·CSV 조회를 로컬 웹에 연결했고 Pages용 저장 결과도 준비했습니다. 사용자 승인 후 서울 Supabase SQL 적용·공개 입력 등록·실제 Auth→워커→5개 비공개 다운로드/해시·접근 거부 및 기존 합성 실행을 검증했습니다. 배포 화면에서도 새 실행과 보고서 다운로드를 확인했습니다. 워커는 현재 개발 PC에서 실행합니다. [실행·저장 계약·검증·남은 작업](docs/FULLSTACK.md). Naive MAE 178.269에 비해 선택 모델 182.500으로 개선되지 않은 결과를 보존했습니다. 실제 재고·조달원가·품절은 미확보이며 기본 재고 비교는 금액 없는 수량 시나리오입니다.


## U21 디지털 샘플 생성

두 번째 탭의 U21에서 U20 명세로 규칙 기반2D·실제GLB 후보를 생성하고, 공개 ABO 쿠션3종의 가상 치수 변환과 비교합니다. 로컬은 새 생성/저장, Pages는 입력9개·후보18개의 저장 결과 조회입니다. [생성 계약·실행·출처·한계](docs/GENERATION.md). 별도 AI 경로에서 CLIP 픽셀 해석과 SD1.5 image-to-image를 추가했습니다. 아래 안내를 확인하세요. U22 합성 검토와 U23 수동 패턴/BOM 연결을 추가했습니다. 현업 승인·봉제/효과 검증은 후속입니다.

## U21 AI 원화 해석·이미지 생성

CLIP의7상품군 후보와 Stable Diffusion1.5의 원화 기반2D 생성을 연결했습니다. 두 생성 강도를 비교하고 모델/입력/출력 해시·시드/설정·조건별 검토 항목을 확인합니다. 별도 AI 런타임이 있는 로컬 PC는 새 추론을 실행하며 Pages는 실제 저장 추론만 조회합니다. 합성6종 중3종/PNG6개 성공,3종은 모델 안전성 검사에서 제외돼 실패로 남겼습니다. [환경 준비·모델/라이선스·API·검증·한계](docs/AI_SAMPLING.md). 학습된 모델의 추론이며 신규 학습·AI 3D·제작 승인 기능은 아닙니다.

## U22 디지털 샘플 검토·수정·승인

두 번째 탭에서 완료한 자체 합성 U21 후보를 등록하고, 조건별 검토→수정 요청→다른 후보의 새 버전→재검토→가상 디지털 승인/철회를 기록합니다. 수정본·명세 변경 시 현재 승인이 무효화되며 이전 이력은 보존합니다. 로컬은 SQLite에 저장하고 Pages는 합성6종/12버전의 저장 이력을 조회합니다. 역할 선택은 합성 시뮬레이션이며 실제 인증·기업/제작 승인은 후속입니다. [실행·역할/상태·API·불변 이력·한계](docs/SAMPLE_REVIEWS.md).

## U23 승인 샘플·패턴/BOM 연결

현재 유효한 U22 승인을 합성 패턴·조각·자재/수량 버전에 고정하고 누락/중복·단위·수량/면적·변경 영향을 검사합니다. 로컬은 연결/해시 이력 저장, Pages는 6제품/12묶음·승인2제품의 연결4버전을 조회합니다. 기존 PAT 윤곽과 샘플의 대응은 수동 합성 가정이며 자동 패턴 생성·봉제/기업 승인·실제 원단 소요량은 미검증입니다. [계약·실행·감사·무효화·API·재현](docs/PATTERN_LINKS.md).

## U24 디지털 샘플링 효과 측정·보고

U20 가상 현행과 합성 시범의 제작 개수/사건 횟수·개발 달력시간·BOM 오류 수정/정상 변경을 구분하고 지표별 동일 제품 짝·분모/제외·0/미측정을 계산합니다. U22/U23 출처 상태가 바뀌면 현재 비교를 다시 계산하며 저장 당시 보고/JSON·CSV·Markdown은 보존합니다. 로컬은 합성 JSON 검증/버전 저장, Pages는 6제품/보고2버전의 저장 조회입니다. 실제 기업/인과 효과·BOM 정확도/비용은 미측정입니다. [계약·기준·운영·API·재현](docs/SAMPLING_EFFECTS.md).

## 브라우저 합성 파일·제품 코드 감사 연결

첫째 탭에서 자체 합성 주간 JSON 또는 ID 대응/원천 묶음을 검증·불변 등록하고, 파일별로 기존 예측/재고 계산과5개 보고 파일을 실행/다운로드합니다. ID 경로는 감사 전부 통과·최초 관측 전 대응표·완결 그리드에서만 연결합니다. 로컬 고정 역할 시뮬레이션이며 Supabase 멤버 업로드/기업 ERP는 후속입니다. Pages는12대응/960원천→6 SKU×80주 저장 예제를 조회합니다. [계약·역할·취소/재시도·출처·큐·API·재현](docs/FORECAST_FILES.md).
