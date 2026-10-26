# 연구 근거와 실제 적용 범위

특정 논문 코드를 복제한 구현은 없다. 아래를 지표·평가·자료 출처로 연결한다.

| 연구/공식 자료 | 현재 코드 적용 | 아직 하지 않은 것 |
|---|---|---|
| Hyndman & Koehler, Another look at measures of forecast accuracy, 2006, [저자 PDF](https://robjhyndman.com/papers/mase.pdf) | forecast.py의 학습 구간 기반 MASE와 0분모 제외 | 논문 전체 실험 재현 |
| Makridakis 외, The M4 Competition: 100,000 time series and 61 forecasting methods, 2020, [DOI](https://doi.org/10.1016/j.ijforecast.2019.04.014), [공식 데이터](https://github.com/Mcompetitions/M4-methods) | naive·계절 naive 비교의 참조, prepare_data.py에서 Weekly Train 변동의 블록 재표집 | M4 전체 대회 재현·OWA·M4 최종 점수 비교. 합성 m=52와 M4 weekly m=1을 혼동하지 않음 |
| Ingel 외, Correlated daily time series and forecasting in the M4 competition, 2020, [저자 공개본](https://arxiv.org/abs/2003.12796) | 시간 경계·계열 간 누수 방지 원칙의 참조 | correlator·통계 앙상블. 내려받은 주간 자료는 논문의 일별 실험과 다른 빈도 |
| Ha & Eck, A Neural Representation of Sketch Drawings, 2017/ICLR2018, [Google Research](https://research.google/pubs/a-neural-representation-of-sketch-drawings/), [공식 데이터](https://github.com/googlecreativelab/quickdraw-dataset) | 공개 스케치 900개 표본에서 split을 나누고 회전/크기 변형해 아트워크 생성 | sketch-rnn 학습·논문 quickdraw-75 분할 재현·실제 봉제 패턴 추출 |

새 PDF 2편은 프로젝트 과목별 참고자료의 통계·컴퓨터비전 폴더에 원문과 같은 제목의 개요로 정리했다. 기존 MASE 논문은 중복 다운로드하지 않고 기존 보유본을 연결했다. M4 전체 결과 논문은 온라인 서지 참조이며 PDF 확보 완료로 표시하지 않는다. 공식 M4 Competitors Guide는 접근 HTTP 403으로 미확보를 기록했다.

공식 홈페이지 참고: [오로라월드](https://auroraworld.com/ko/business/overview), [공식 Palm Pals 몰](https://palmpals.co.kr/). 공개 제품 사진을 실제 부품 정답으로 취급하지 않으며 원본 사진을 배포하지 않았다. 가상 브랜드/디자인/원가/거래/정답과 실제 상품 사실을 구분한다.

Quick Draw 데이터/파생 아트워크: Google, Inc. / Quick, Draw! contributors, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 변경은 회전·크기 조정이며 실제 Aurora 제품 이미지가 아니다. M4는 주최자 공개 자료이지만 별도의 재배포 라이선스를 임의로 단정하지 않는다. 전체 연구 원본 CSV·논문과 전체 가공 자료는 코드 저장소 밖에 둔다.
