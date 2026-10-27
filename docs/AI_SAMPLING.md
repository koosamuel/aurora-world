# U21 AI 원화 해석·2D 생성

U20의 자체 합성 원화를 **실제 사전학습 모델**에 넣는다. `ai_worker.py`의 CLIP 분류기는 이미지 픽셀만 받으며 제품 ID·파일명·정답 가족군·요구 명세를 분류 입력으로 사용하지 않는다. 7개의 고정 영문 후보와 이미지의 코사인 유사도를 비교한다. 1·2위 차이 0.03 미만은 데모용 모호 구간이며 보정된 확률/인수 기준이 아니다. 항상 사람이 확인한다. 모호한 경우 생성 프롬프트는 일반 plush toy로 제한한다.

원화의 종횡비를 유지해 흰 배경 512×512 PNG로 만든다. 가장자리 색과의 거리로 추정한 주요색은 **규칙 기반 픽셀 휴리스틱**으로 별도 표시한다. CLIP 후보와 이 색상, 제한된 조건 힌트(부드러움·둥근 외형)로 프롬프트를 구성하고 Stable Diffusion 1.5 image-to-image를 실행한다. 자유로운 한국어 이해나 조건 충족 인증이 아니다. 원화에 없는 실측 치수·봉제 부위·원단 물성을 추론하지 않는다.

같은 입력·시드·프롬프트에 강도 0.45/0.70, DDIM, 총 20 step(실제 denoising 9/14), guidance 7.5를 사용한다. 조건별 `satisfied=null`, `design_approved/effect_measured=false`, `dimensions_verified=false`를 보존한다. 결과는 **2D PNG**이며 기존 `generation.py`의 GLB 기하와 독립적이다. AI 3D·패턴/BOM을 생성한 것으로 표시하지 않는다.

## 모델·출처

- [OpenCLIP ViT-B-32 LAION2B](https://huggingface.co/laion/CLIP-ViT-B-32-laion2B-s34B-b79K), MIT, 로컬 revision `1a25a446712ba5ee05982a381eed697ef9b435cf`.
- [Stable Diffusion v1.5](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5), [CreativeML OpenRAIL-M](licenses/CreativeML-OpenRAIL-M.txt), 로컬 revision `451f4fe16113bff5a5d2269ed5ad43b0592e9a14`.
- [Diffusers image-to-image 문서](https://huggingface.co/docs/diffusers/api/pipelines/stable_diffusion/img2img).

기존 PC 캐시를 재사용했다. 가중치는 Git/Pages에 넣지 않는다. `configs/ai/model-manifest.json`에 설정·토크나이저·safetensors 16개(6,087,795,516 bytes)의 크기/SHA-256을 기록하고 추론 전에 전부 재검사한다. 로컬 safetensors만 로드하며 inference 중 자동 다운로드·외부 API 호출은 하지 않는다. SD의 기본 safety checker를 유지하며 제외된 출력은 완료/게시 처리하지 않는다. 이는 제품 안전·저작권 검수 통과를 의미하지 않는다.

## 로컬 실행

기본 예측/기하 서버는 기존 Python 표준 라이브러리 환경을 유지한다. AI는 별도 Python 3.13 런타임이다. 개발 PC에서 MPS/float16으로 확인했으며 CPU/float32 경로는 코드에 있지만 실제 CPU 전체 생성 속도/출력은 미검증이다. 설치에는 패키지 다운로드와 Cairo 네이티브 라이브러리가 필요하다. 이 PC는 `/opt/homebrew/lib/libcairo.dylib`를 사용한다.

```sh
python3.13 -m venv .venv-ai
.venv-ai/bin/python -m pip install -r requirements-ai.txt
```

`.ai-local.example.json`을 참고해 `.ai-local.json`에 **절대 경로**로 `python`, `sd15` 스냅샷 폴더, `clip` 스냅샷 폴더를 설정한다. 실행/모델 경로는 개발자 설정이며 HTTP에서 받지 않는다. `.ai-local.json`과 `.venv-ai/`는 Git 제외다. 런타임 준비 표시와 가중치 검증/실제 추론 성공은 구분한다.

```sh
PYTHONPATH=src python3 -m aurora serve --port 8765
# 저장된 게시 예제 재생성: 새 출력 폴더 필수
PYTHONPATH=src .venv-ai/bin/python tools/build_ai_sampling_demo.py --output results/new-ai-demo
```

두 번째 탭의 **원화에서 AI 이미지 후보로**에서 합성 명세/시드를 선택한다. 새 U20 버전이 등록되면 선택 목록을 갱신한다. 동일 입력/설정/장치 기록을 남기지만 플랫폼/라이브러리 변경 시 비트 동일성을 보장하지 않는다. 새 모델 학습/미세조정은 수행하지 않았다. 회사 원화·사진을 처리하는 경로는 지원하지 않는다.

## API·실패와 저장

- GET `/api/ai-sampling/catalog`: 등록된 자체 합성 U20 명세와 AI 런타임 설정 유무.
- POST `/api/ai-sampling/runs`: `source_id`, `source_checksum`, 정수 `seed`, `request_key`만 허용. 자유 프롬프트·파일 경로·외부 URL은 받지 않는다.
- GET `/api/ai-sampling/runs/{id}`: SQLite의 queued/running/succeeded/failed 상태. 같은 요청 재전송은 같은 실행, 다른 입력의 같은 키는409.
- GET `/api/ai-sampling/artifacts/{id}/{file}`: 성공한 실행의 허용 파일만 크기/해시 검증 후 제공.

AI 작업은 한 번에 하나만 접수한다. 별도 Python 프로세스를 argv로 실행하며 shell은 쓰지 않는다. 600초 제한, 재시작 시 중단 작업은 실패로 표시하고 재시도는 새 요청으로 한다. 새로고침은 진행 중 실행 조회를 복원한다. Host/Origin은 기존 loopback 규칙을 적용한다. 명세/코드/설정/모델명세 해시를 접수 시 고정한다.

로컬 결과는 `results/ai-samples/`, 로그는 같은 폴더의 실행 ID별 `.log`다. 실패/부분 출력은 API 다운로드를 허용하지 않는다. 성공 산출물은 `input.json/png`, `preserve.png`, `reinterpret.png`, `analysis.json`, `report.json`, `models.json`, `artifacts.json`이다. 보고서에는 입력/출력 분류 후보·시간·시드·프롬프트/부정 프롬프트·모델 파일 해시·라이브러리 버전·장치·한계를 담는다. 유사도/픽셀 차이는 진단치이고 품질 점수가 아니다.

Pages는 `client/demo/ai-sampling/`의 **실제로 추론한 저장 결과**를 조회한다. 새 추론을 실행하거나 Supabase에 DS 작업을 저장하지 않는다. 저장 결과6건 중 토끼·고양이·과일형3건/PNG6개는 성공, 젖소·강아지·선인장형3건은 safety checker 제외로 실패했다. 실패 이미지는 게시하지 않으며 실패 사실은 선택 화면/실행JSON에 보존한다. 이6건은 개발용 합성 예제이며 독립 정확도·일반화/FID·현업 품질·수정량·절감 효과를 평가한 표본이 아니다.

## 검증과 남은 범위

기본 Python 검사에는 AI 패키지가 필요하지 않다. 요청 충돌·활성 작업 제한·중단/시간 초과·모델 손상 거부·외부/기업 입력 거부·모호 후보/조건 힌트·실제 저장 이미지 해시를 검사한다. 별도로 로컬 HTTP 새 추론과 브라우저의 원화/이미지 비교·다운로드·실패·새로고침/모바일·Pages 저장 전용을 검증한다.

U21 전체는 부분 구현이다. 자유로운 원화 해석·조건 준수/유사 복제/다양성·현업 수정량·메모리/비용의 체계적 비교, AI 3D와 U22 승인·U23 패턴/BOM·U24 효과, 회사 입력/권한·Supabase DS 저장/원격 워커가 남아 있다. 기존 DEM 실서버와 SQL은 이 AI 경로와 분리한다.
