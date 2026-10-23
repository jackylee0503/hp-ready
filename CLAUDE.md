# HP-Ready Triage – 해커톤 프로젝트 (nuuEnergy 챌린지)

## 한 줄 요약

고지서·건물정보·사진으로 "이 집에 히트펌프 되냐"를 3분 안에 정직하게 답한다.
LLM은 사진/고지서를 **읽기만** 하고, 판정·비용은 **물리 계산 엔진**이 한다.
모르는 건 범위로 두고, 결과를 가장 크게 바꾸는 **사진 딱 하나**만 요청한다.
남는 불확실성은 **기사 브리핑**으로 넘긴다 → 방문을 없애는 게 아니라 짧고 정확하게 만든다.

## 핵심 원칙 (절대 어기지 말 것)

1. **LLM은 파서다.** 스키마 칸만 채운다. 판정·추천·계산 금지.
2. **모르면 비운다.** 확신 없는 칸은 null. 칸마다 confidence(0~1).
3. **판정은 engine.py가 한다.** 물리 계산 + 몬테카를로. 3채 기준값으로 보정.
4. **필요한 것만 묻는다.** 신호등 확률을 가장 크게 흔드는 미지 인자 하나만 사진 미션으로.
5. **스키마 = 계약서.** 인자는 `schema.py` 한 곳에만 정의.
6. **숫자는 지어내지 않는다.** 단가·JAZ는 아래 고정 가정만 사용. 설치비·보조금 금액은 출력하지 않음("기사 견적 필요").
7. **빨강을 남발하지 않는다.** 빨강엔 반드시 이유 카테고리 + "이걸 하면 노랑 됨" 경로를 붙인다.

## 상황

* 10시간 해커톤 (아래 타임라인).
* 산출물: ① 브라우저에서 도는 프로토타입 ② **평가용 2채 결과**(피치에서 보여줌) ③ 슬라이드 아닌 라이브 데모.
* 데이터: 실제 건물 5채(CSV + JSON), 익명화됨(이름·주소 없음, PLZ 지역 단위, 면적·소비량 반올림). 3채(`buildings_dev`, `data/buildings_dev.csv`)는 기준값 `reference_heating_load_kw` + `expected_verdict`(green/yellow/red만, unclear 없음), 2채는 기준값 숨김(심사용). **사진 없음** — 입력은 "집주인이 현실적으로 아는 것", 빈 값 = 기록 안 됨.
* 주최 측 명시: **"Some cases are deliberately contradictory."** → 모순 점검(엔진 2b)이 채점 포인트.
* 코드 품질·테스트 신경 안 씀. 데모가 안 터지는 것만 중요.

## 심사 기준 → 우리가 점수 따는 곳

| 기준 | 점수 | 우리 무기 |
| --- | --- | --- |
| Technical execution & reliability | 25 | Cloud 배포 + Demo mode 캐시 + JSON 경로로 사진 없이도 2채 돌아감 |
| Problem-solution fit & user value | 25 | 3분, 집주인 한 문장 이유, 비용 범위, 기사 브리핑 |
| Explainability & handling uncertainty | 20 | 모든 출력이 범위 + 신호등 확률, `unclear` 허용, "기사가 X·Y 확인" |
| Innovation & smart use of technology | 15 | LLM=센서 / 물리=판정 분리, 엔트로피 기반 "사진 하나만" |
| Feasibility & scalability | 15 | 건물당 API 1회(메모, 캐시), 같은 함수로 어떤 리드 CSV든 우선순위표, 고정 가정 교체만으로 확장, Phase 2 실방문 데이터 보정 |

심사 측 명시: "모르겠다, 기사가 X·Y 확인해야 함"이 자신 있게 틀린 숫자보다 낫다 → `unclear`는 실패가 아니라 기능. 단 채점 enum은 green/yellow/red뿐 → 항상 `best_color`를 내고 `unclear`·모순은 옆에 플래그로.
Key terms에 Heizlast(가장 추운 날 필요 kW), Vorlauftemperatur, JAZ, 단관/복관이 명시됨 → 출력에 이 네 개가 반드시 보이게.

## 우선순위 (이 순서대로만 만든다. 위가 안 돌면 아래 손대지 않음)

* **P0-a 채점 경로**: `loader.py`(CSV/JSON → House, 텍스트 칸은 **LLM NotesObs가 주 경로** + 정규식) → `engine.py`(면적·연식 부하, 모순 점검, 산술 근사식, **간단 몬테카를로**, JAZ 구간, 비용, 신호등, 이유) → `calibrate.py`(k 1개) → 📊 Evaluation 탭
  * 텍스트 칸(`building_notes`, `radiator_info`, `energy_carrier_detail`): 숫자(라디에이터 개수, 밸브, 리터, U값)는 정규식. 사실(보조 열원·태양열·미사용 공간·단열 조치·개조 정황)은 **LLM `NotesObs`가 주 경로**(CEO D9 — 숨은 2채가 Kachelofen·Dachgeschoss ungenutzt처럼 다르게 써도 잡도록, 그리고 "AI가 판단하나?"에 AI가 보이도록) → `data/notes_cache.json`에 저장(5채 = 호출 5번). 키워드는 API 실패 시 대체. 화면에 "AI가 메모에서 찾은 사실 + 원문 인용" 표시
  * **간단 몬테카를로 (CEO D10, P0)**: N=500, seed 0, numpy 벡터. 불확실값 = 면적당 부하 × U(0.8, 1.2), 라디에이터 크기 모름이면 small/medium/large를 **0.25/0.5/0.25** [estimated] 로 뽑고 × U(0.85, 1.15), 미사용 공간이면 면적 × U(0.7, 1.0). 출력: 색 확률, 공급온도·부하 p10/p50/p90
  * Evaluation 탭: 3채 기준값 vs 우리 값(오차 %) + **leave-one-out**(2채로 보정 → 나머지 1채 예측, 3번 반복) + 평가 2채 결과(범위 포함)
  * 모든 결과에 **`Rechenweg` expander**: 면적 × 연식 W/m² × k → 난방부하 (옆에 소비량 기반 부하 비교) → 라디에이터 ΣΦ_n → 필요 공급온도 → JAZ → 비용, 각 단계 숫자와 쓴 가정 + 발견한 모순과 어느 쪽을 믿었는지
  * **API 없이도 돌아야 함**: `notes_cache.json`을 행사 초반에 한 번 만들어 커밋 → 이후엔 캐시로 결정론. 캐시·API 둘 다 없으면 키워드 대체(화면에 "규칙 분석" 표시)
  * **P0-a 안에서 자르는 순서** (시간 부족 시 뒤에서부터): Rechenweg 상세 → leave-one-out 표 → 모순 규칙 일부(핵심: ±40%·보조 열원·미사용 공간·U값 개조 정황은 유지). LLM NotesObs와 몬테카를로는 자르지 않는다
* **P0-b 🔧 기사 방문 준비서 (CEO E1)**: Installer 탭. 엔진 출력만 묶음(새 계산 최소): 방문 유형 + 준비물 + 현장 확인 항목 (엔진 9 참고). 건물 선택 목록 = loader의 5채 + 일괄 업로드 행 + Homeowner 세션의 집. nuuEnergy는 자체 기사팀으로 설치하는 회사 → "기사가 출발 전에 뭘 들고 갈지 안다"가 가장 직접적인 가치
* **(P2로 미룸, CEO D11) 리드 일괄 분류 (CEO E2)**: P0에서는 Evaluation 탭의 5채 표에 `lead_score`·방문 유형 열만 추가하고 피치에서 "같은 함수로 어떤 CSV든"이라고 한 문장. 아래 업로드 기능은 시간 남을 때만 — Evaluation 탭 아래에 `st.file_uploader`로 같은 형식 CSV 업로드 → 행마다 evaluate → **방문 우선순위 표**(lead_score 높은 순) + 방문 유형 열 + `st.download_button`으로 CSV 내보내기. **LLM 호출 0회**(CEO D6): 메모는 정규식 + 키워드(wood stove/Kaminofen/Holzofen, solar/Solarthermie, not lived in/unbewohnt, insulat/gedämmt, preset/voreingestellt, balanced/abgeglichen)만, 표에 "규칙 분석" 표시. 행마다 try/except → 실패 행은 오류 열에 이유, 최대 200행, 기준값 열은 없어도 됨, 인코딩 utf-8 → 실패 시 latin-1. 피치: "nuuEnergy가 매일 받는 리드 100건도 이렇게"
* **P0-c 🏠 Homeowner (드롭다운만)**: 드롭다운 입력 → 신호등(색 확률)·이유·비용·기사 체크리스트·**공급온도 스케일(p10–p90 밴드)**
  * 공급온도 스케일: 가로 막대 35→70°C, 구간 색(바닥난방·≤55 초록 / 55–60 노랑 / >60 빨강), 우리 추정값에 마커. 판정은 3색 그대로, 스케일은 보조
* **P1** (CEO D5로 사진 흐름 이동): 고지서·라디에이터 사진 추출(미션별 스키마, merge) + Demo mode 캐시 → 다음 질문(엔트로피 ÷ effort). 몬테카를로는 P0-a로 이동(CEO D10)
* **P2**: 사진 재촬영 루프(`missing_reason` 안내·재시도 — CEO R1로 P1에서 이동, 데이터에 사진 없음), Installer 탭 디자인 다듬기, 외관 사진, 도일법 병행, 대수평균 수치해, 선택 사진 4~6
* **컷**: PLZ별 설계온도/도일 조회(상수 하나로), 세밀한 라디에이터 룩업(작/중/대 3단계로)

## 타임라인 (10h)

**마감 기준 역산 규칙**: 행사 시작하면 제일 먼저 제출 마감·발표 순서/시간을 확인한다. 실제 빌드 가능 시간 = 마감 − 개회·팀빌딩 − 1.5h(동결·피치). 10h보다 짧으면 P1부터 자르고, 아래 표의 비율대로 다시 나눈다.

| 시간 | 할 일 |
| --- | --- |
| 0:00–0:30 | 데이터 열어보고 스키마 필드명·기준값 형식 맞추기 |
| 0:30–3:00 | P0-a: loader + engine + calibrate + Evaluation 탭 → **여기서 2채 결과 확보** |
| 3:00–4:00 | P0-b 🔧 Installer 준비서 (+ P0-a가 밀렸으면 여기까지 버퍼) |
| 4:00–5:00 | P0-c 🏠 Homeowner (드롭다운) |
| 5:00–7:30 | P1: 사진 추출 → 다음 질문 (자를 땐 뒤에서부터) |
| 7:30–8:30 | Cloud 재배포 확인, 데모 캐시 고정, 해피패스 3회 리허설 (Cloud 첫 배포는 행사 전날 빈 앱으로 끝내둠) |
| 8:30 | **코드 동결** |
| 8:30–10:00 | 피치 준비·리허설 |

## 행사 전 마일스톤 (에이전트: 세션 시작 시 여기부터 확인하고, 안 끝난 첫 항목을 사용자에게 알려줄 것)

- [x] M0 리포·venv·의존성 (`C:\dev\hp-ready`, 비공개 GitHub, Smart App Control 때문에 pandas<3·pyarrow<22·pillow<12 고정)
- [x] M1 eng review 반영 (16f8578) + 라디에이터 정격 표 출처 확인 (Kermi/Buderus EN 442)
- [ ] M2 **API 확인 (행사 전 필수 — LLM 메모 읽기가 P0 핵심, CEO D9)** — `.streamlit/secrets.toml`에 `ANTHROPIC_API_KEY = "..."` (사용자가 직접 붙여넣기), `claude-sonnet-5-5`로 실제 호출 1회 성공. 실패하면 응답 오류 원문 보고 모델 ID부터 확인
- [x] M3 **Cloud 첫 배포** (전날 성공, "HP-Ready (setup)" 화면 확인. 남은 것: Secrets에 키 넣기는 M2와 함께, URL 기입) — share.streamlit.io → New app → `jackylee0503/hp-ready`, branch `main`, file `app.py`, Advanced settings에서 Python 3.11 + Secrets에 키 입력 → URL에서 "HP-Ready (setup)" 화면 확인. URL을 여기 적기: `(배포 후 기입)`
- [x] M1b dev 데이터 반영 (`data/buildings_dev.csv`, 면적·연식 부하 k=1.01, 모순 점검 규칙, U값 개조 정황, P0 몬테카를로 → dev 3/3)
- [ ] M4 **데모 사진** — 우선순위 낮아짐(데이터엔 사진 없음, 보너스 장면용). 고지서 1장 + 큰 라디에이터 1~2장이면 충분 (`samples/`에 저장, 원본은 gitignore됨):
  - [ ] 고지서 1장: 연간 kWh 또는 m³·청구기간이 보이는 스크린샷/사진. 이름·주소·고객번호는 가리기
  - [ ] 큰 라디에이터 (Typ 22 긴 것 또는 Typ 33): 비스듬히 + 아래 배관까지 나온 사진 1장 (배관 잘린 사진은 P2 재촬영용, 선택)
  - [ ] 엉뚱한 사진 1장 (고양이·컵 등) → `wrong_object` 시연용
  - [ ] (선택) 집 외관 1장
- [ ] M5 행사 당일 첫 30분: 제출 마감·발표 시간 확인 → 타임라인 역산, 데이터 사용 조건 확인, **미리 짠 코드 허용 여부 반드시 질문** (`/intake`로 입력). 허용 안 되면: 리포의 `app.py`는 빈 껍데기라 그대로 두고, k=1.01·표·규칙은 "사전 조사(문서)"로만 쓰고 코드는 당일 작성 — 이 경우 P0-c·P1부터 자름

## 스택

* Python, Streamlit, Pydantic, pandas, numpy, Anthropic API
* 모델: `claude-sonnet-5-5` (비전 + 구조화 출력)
* API 키: `st.secrets["ANTHROPIC_API_KEY"]` 우선, 없으면 환경변수. 하드코딩 금지.
* 배포: Streamlit Community Cloud에 미리 올려둔다 (로컬 백업 유지). Python 3.11 지정. 리포는 비공개 유지. 발표 10분 전 Cloud 앱을 열어 깨워둔다(잠든 앱 콜드스타트 ~1분).
* 데이터: `data/`는 nuuEnergy에 사용 조건 확인 후 커밋(Cloud Evaluation 탭에 필요). 공개 금지면 Evaluation은 로컬로 시연. 고지서·사진 원본(`samples/*.jpg|png|pdf|heic`)은 gitignore — 개인정보 가린 버전만 `git add -f`.

## 파일 구조 (이 외에 새 파일 만들지 말 것)

* `schema.py`    – Pydantic: `House`(입력), `Result`(출력), 고정 가정 상수, 인자→사진 미션 문구
* `extract.py`   – 사진/고지서 → `House` 부분 채움 + confidence. **미션별 작은 스키마**(`BillObs`, `RadiatorObs`, `ExteriorObs`, schema.py에 정의)를 tool use로 강제 → 그 사진에 보일 수 있는 칸만 + 칸별 `missing` 코드. `source`는 app이 채움(LLM 아님). 결과를 House로 매핑해서 반환. 전송 전 Pillow로 긴 변 1568px JPEG 변환(HEIC는 실패 시 "JPG로 다시" 안내)
* `loader.py`    – 제공된 CSV/JSON → `House` (심사용 경로. 사진 없이 돌아야 함)
* `engine.py`    – 게이트, 물리 계산, 몬테카를로, 신호등, 다음 질문, 기사 브리핑
* `calibrate.py` – 3채 기준값과 엔진 출력 비교, 보정 파라미터 조정 (한 번 돌리고 값만 engine에 박음). **과적합 주의: 점 3개 → 파라미터 딱 1개만 보정** (2개면 leave-one-out의 2채에 정확히 맞아 검증 의미 없음). 기준값이 난방부하이므로 면적·연식법의 `k` 하나(로그 비율 기하평균). 나머지는 문헌 기본값 고정
* `app.py`       – Streamlit. 탭 3개: `🏠 Homeowner` / `🔧 Installer` / `📊 Evaluation`
* `requirements.txt`, `.gitignore` – 이미 있음. 패키지 추가 시 requirements.txt에도 추가
* `.claude/commands/` – 슬래시 커맨드 `intake`, `check`, `hp-review` (아래 작업 방식 참고)
* `.streamlit/secrets.toml` – 로컬 API 키 (gitignore됨, 커밋 금지). Cloud에선 앱 설정의 Secrets에 입력
* `data/`        – 제공된 5채 원본 (`buildings_dev.csv` 받음) + `notes_cache.json`(텍스트 칸 LLM 추출 캐시)
* `samples/`     – 데모용 사진·고지서, 캐시된 추출 결과 `samples/cached_extract.json`

## 인터페이스 계약 (함수 시그니처 고정. 이것만 지키면 엔진·UI를 병렬로 만들 수 있음)

```python
# schema.py
class House(BaseModel):
    # 값 필드는 아래 스키마 초안대로, 전부 Optional
    confidence: dict[str, float] = {}      # 필드명 → 0~1
    source: dict[str, str] = {}            # 필드명 → dropdown | photo | bill | data | prior
    missing: dict[str, str] = {}           # 필드명 → not_visible | blurry | ambiguous | wrong_object
class Params(BaseModel): ...               # k(유일한 보정값, 기본 1.01), η, 온수, 단관 패널티 등 상수
class Step(BaseModel): label: str; value: str; assumption: str | None
class Result(BaseModel): ...               # 아래 Result 초안 + trace: list[Step] (Rechenweg)

# loader.py
def load_buildings(path="data/") -> list[tuple[str, House, dict | None]]   # (id, House, 기준값 or None)

# extract.py
def extract(file_bytes: bytes, mime: str, mission: str) -> House           # 부분 채움 + missing
def merge(base: House, new: House) -> House                                # 필드별 출처 우선순위(아래), 같은 출처끼리만 confidence로

# engine.py
def evaluate(h: House, p: Params = DEFAULT) -> Result                      # P0 점추정
def evaluate_mc(h: House, p: Params = DEFAULT, n=500, seed=0) -> Result    # P1, seed 고정 = 결정론
def next_question(h: House) -> str | None                                  # 다음에 물을 필드명
def installer_brief(h: House, r: Result) -> Result                         # visit_type, parts, installer_checklist 채워서 반환

# calibrate.py
def fit(buildings) -> Params
def leave_one_out(buildings) -> pd.DataFrame
```

`python engine.py` 단독 실행 시: 예시 집(1972 연립 140m², 부분 개조, 가스 18,000 kWh, 3인, 라디에이터 중간 8개 → 약 69°C 🔴가 정상) + dev 3채으로 evaluate 결과와 Rechenweg 출력 (스모크 체크용).

## 고정 가정 (챌린지 제공, 변경 금지) → `schema.py` 상수

| 항목 | 값 |
| --- | --- |
| 히트펌프 전기 | 0.26 €/kWh |
| 가스 | 0.11 €/kWh |
| 난방유 | 1.70 €/L (≈ 10 kWh/L → 0.17 €/kWh) |
| JAZ 바닥난방 | 4.0 |
| JAZ 라디에이터 ≤55°C | 3.5 |
| JAZ 라디에이터 55~60°C | 2.8 |
| 라디에이터 >60°C | 표에 없음 → 판정상 빨강(조치 필요) |

참고: 가스 열단가 ≈ 0.11/η ≈ 12.2 ct/kWh(η=0.9). HP 최악 칸(2.8)도 9.3 ct → ≤60°C 안에선 항상 운영비 이득. 손익분기 JAZ ≈ 2.1.

## 스키마 초안 (`schema.py`) – 제공 CSV/JSON 컬럼명에 맞춰 이름 조정할 것

**CSV 컬럼 → House 매핑** (loader.py, 코드를 데이터에 맞춘다):

| CSV | House | 비고 |
| --- | --- | --- |
| `construction_year` | `build_year` | |
| `floor_area_m2` | `living_area_m2` | 반올림된 값 |
| `renovation_status` | `renovation` (unrenovated/partially/fully/None) | 자주 빈 값 |
| `heat_distribution` | `heat_distribution` | |
| `annual_consumption_kwh` | `annual_fuel_kwh` | |
| `energy_carrier` + `energy_carrier_detail` | `fuel_type` (gas/lpg/oil/district/electric) | detail에 "LPG"/"Flüssiggas"면 lpg, "litres"면 리터 숫자도 추출해 kWh와 대조 |
| `radiator_info` | `radiator_count` (+ `valves_to_replace`, `hydraulic_balanced`) | 정규식 `(\d+)\s*radiators?` (단수 "1 radiator" 포함), `(\d+)\s*valves` |
| `pipe_system` | `pipe_system` | `unknown` → None |
| `flow_temperature_c` | `current_flow_temp_c` | 자주 빈 값 |
| `persons_in_household` | `occupants` | |
| `hot_water_via_heating` | `dhw_by_boiler` | yes/no |
| `rooms` | `rooms` | 개수 없을 때 라디에이터 수 추정용 |
| `building_notes` | `notes` + `NotesObs` (아래) | LLM이 사실만 추출, 캐시 |
| `location` | `region` | "Munich area (82xxx)" → munich / hamburg / … |
| `reference_heating_load_kw`, `expected_verdict` | (loader가 기준값 dict로 따로 반환) | dev 3채만 |

`NotesObs` (LLM이 `building_notes`에서 뽑는 사실, 판정 금지): `u_values` {windows, wall, roof, floor, basement}, `extra_heat_source` (wood_stove/tiled_stove/heat_pump/none), `extra_source_all_winter` (bool), `solar_thermal_dhw` (bool), `unheated_area_note` (str, 예: "top floor not lived in"), `insulation_measures` (list: cavity_wall/roof/windows/…), `glazing` (str). 칸마다 원문 인용 `evidence` 한 줄.

`House` (전부 Optional, 각 필드에 confidence):

* `fuel_type` (gas | lpg | oil | district | electric)
* `annual_fuel_kwh` (float) – engine이 아래 원본 값에서 계산 (LLM이 직접 채우지 않음). loader 경로는 데이터 값 그대로
* 고지서 원본(`BillObs`): `kwh_printed`, `m3`, `zustandszahl`, `brennwert`, `liters`, `period_start`, `period_end` – 보이는 숫자 그대로, 계산 금지
* `build_year` (int)
* `building_type` (detached | semi_detached | terraced | multi_family)
* `living_area_m2` (float)
* `occupants` (int)
* `dhw_by_boiler` (bool) – 온수도 보일러로 데우는지
* `monthly_advance_eur` (float) – 월 선납금(Abschlag). 고지서 없을 때 대체 입력
* `boiler_condensing` (bool) – 콘덴싱(Brennwert) 여부, 보일러 앞면 사진
* `heat_distribution` (underfloor | radiators | mixed)
* `pipe_system` (two_pipe | single_pipe) – 단관/복관
* `radiator_size` (small | medium | large) 또는 `radiator_type` + 치수 – 사진(콘센트·창틀 기준, A4 선택) 또는 그림 드롭다운
* `radiator_count` (int) – 드롭다운 / `radiator_info` 정규식
* `valves_to_replace` (int) – `radiator_info` 정규식 `(\d+)\s*valves`
* `hydraulic_balanced` (bool) – `radiator_info`에 "balanced"/"abgeglichen" → True / "preset"/"voreingestellt"만 있으면 None + 메모 "프리셋 밸브 있음(밸런싱 확인 필요)" / 없으면 None
* `windows` (original | double_renovated | triple)
* `roof_insulated`, `walls_insulated` (bool)
* 현장 플래그: `listed_building`, `outdoor_unit_space`, `flat_level_gas_heating` (bool)

`Result`:

* `traffic_light` (green | yellow | red | unclear) + `best_color` (green | yellow | red, 항상 채움 = MC p50의 색) + `boundary` (bool, 최대 확률 < 0.6) + `reason`(집주인용 한 문장) + `reason_category` (temperature | insulation_first; site_flags는 노랑 캡 사유로만 reason에 언급)
* `p_green`, `p_yellow`, `p_red` (몬테카를로 비율)
* `required_flow_temp_c` (p10~p90 범위)
* `heat_load_kw` (범위)
* `jaz_bucket` (4.0 | 3.5 | 2.8 | none)
* `cost_now_eur`, `cost_hp_eur`, `saving_eur` (범위)
* `next_photo` (집주인 미션 1개)
* `installer_checklist` (기사 현장 확인 리스트)
* `site_flags` (문화재 / 실외기 공간 / 층별 가스 — 확정된 것만)
* `contradictions`: list[{`what`, `sources`, `trusted`, `why`}] — 엔진 2b가 채움. 집주인 화면·Rechenweg·기사 브리핑에 표시
* `confidence` (0~1), `lead_score` (0~1), `visit_type` (remote_quote | visit_with_parts | hold), `parts`: {`radiators_to_swap`: (lo, mid, hi), `valves`: int|None, `balancing`: needed|check|None} — 엔진 9
* `installer_checklist` = 현장 확인 항목 list[str]. Installer 탭은 `visit_type` + `parts` + `installer_checklist`로 그림 (`installer_brief()`는 이 셋을 채우는 함수)
* **점추정은 항상 채운다**: `unclear`여도 `best_color`(가장 가능성 높은 색), `required_flow_temp_c`·`heat_load_kw` 점값을 같이 낸다. Evaluation 탭은 이 점값으로 기준값과 비교하고 `unclear`는 옆에 플래그로만 표시

## 엔진 로직 (`engine.py`)

**0. 게이트 (규칙)**
`listed_building`, `outdoor_unit_space == False`, `flat_level_gas_heating` 은 **빨강 사유가 아니다** (문화재는 허가로, 공간 부족은 실내기/스플릿으로, 층별 가스는 개별 검토로 대개 해결). 확정되면 신호등은 물리 결과 그대로 두고 `site_flags`에 추가 + 기사 체크리스트 맨 위 + 초록이면 최대 노랑으로 캡. 멘토/데이터가 하드 스톱이라고 명시할 때만 빨강.

**1. 연료 → 열**
고지서 없고 선납금만 있으면: `annual_fuel_kwh ≈ monthly_advance_eur × 12 / 연료단가`, 범위 넓게(기본요금·실제 단가 차이로 −30%~+10%), confidence 낮게.
**고지서 환산은 engine이 한다** (LLM은 원본 숫자만): `kwh_printed`가 있으면 그대로, 없으면 `m3 × zustandszahl × brennwert`, 기름은 `liters × 10`. 청구기간이 365일이 아니면 `× 365 / 일수`. 각 단계는 Rechenweg에 표시.
`Q_heat = annual_fuel_kwh × η` — **가스 고지서 kWh는 상위발열량(Hs) 기준**이므로 η도 Hs 기준: 콘덴싱 0.88 / 비콘덴싱 0.80 / 모름 0.84. 기름(10 kWh/L)은 하위발열량(Hi) 기준: 콘덴싱 0.95 / 비콘덴싱 0.85 / 모름 0.9. Rechenweg에 "Hs/Hi 기준" 명시. 보정 대상 아님(문헌값 고정).
`Q_space = Q_heat − Q_dhw` (dhw_by_boiler면 `Q_dhw ≈ 600 kWh × occupants`, 태양열 온수 있으면 절반)
**연료 종류별**: lpg는 가스와 같은 η(Hs)·단가 0.11 적용하되 Rechenweg에 "LPG 실제 단가는 더 높을 수 있음, 고정 가정 사용" 표시. `district`(지역난방)·`electric`(직접 전기난방)은 η = 1.0, **현재 비용은 "단가 미제공"**(고정 가정표에 없음, 지어내지 않음) — 부하·판정·HP 비용만 계산.
**`current_flow_temp_c`(데이터의 현재 보일러 설정)**: 있으면 Rechenweg·기사 브리핑에 표시. 판정에 직접 쓰지 않음(보일러는 보통 필요 이상으로 높게 설정됨). 단 우리 계산값이 현재 설정보다 10 K 넘게 높으면 모순으로 기록(현재 그 온도로 집이 데워지고 있으므로 계산이 과대).

**판정 측도 정의 (피치·UI에 명시)**
"필요 공급온도" = **설계 외기온도(Normaußentemperatur, DIN/TS 12831-1, 지역별)일 때, 기존 라디에이터로 실내 20°C를 유지하는 데 필요한 공급수 온도** (= Auslegungsvorlauftemperatur).
55/60°C 경계는 우리가 정한 게 아니라 챌린지 JAZ 표의 구간. 표가 60°C에서 끝나므로 >60은 "고정 가정 밖 → 조치 필요".

**2. 난방부하 (Heizlast) — 면적·연식 기반이 주, 소비량은 교차 확인**
dev 3채에서 소비량 방식은 맞춰야 할 t_vbh가 625 / 1,157 / 2,400 h로 4배 벌어짐(장작난로·사용 습관 탓) → 파라미터 1개로 보정 불가. 기준값은 면적당 49 / 54 / 72 W/m²로 연식과 함께 움직임.
* **(주) 면적·연식법**: `P_load = k × w(연식, 개조) × living_area_m2`
  | 연식 | 미개조/모름 W/m² | 부분·전면 개조 W/m² |
  | --- | --- | --- |
  | ≤1977 | 130 | 80 |
  | 1978–1994 | 85 | 70 |
  | 1995–2001 | 60 | 55 |
  | 2002–2015 | 50 | 50 |
  | ≥2016 | 35 | 35 |
  출처: 독일 업계 경험값(BDH/VdZ: 1977 이전 130 (120–180), WSchV 1995–2001 60 (50–80), EnEV 2002–2015 50 (40–60), 부분 개조 60–100; Viessmann 표 EFH 1969–73 150, 1974–77 115, ab 1995 60). "DIN EN 12831 대체 아님, 1차 추정용"이라고 UI에 표시. MC 범위: 표값 ±20%.
  **"부분 개조" 칸을 쓰는 경우** (renovation이 비어 있어도): ① `NotesObs`에 명시적 단열 조치(cavity wall, roof insulated, new windows 등) 또는 ② **벽 U값이 연식 기준의 0.7배보다 낮음** (CEO D8). 연식 기준 벽 U값(대략, [estimated] WSchV/EnEV 부위 요구치 수준): ≤1977 1.0 / 1978–94 0.6 / 1995–2001 0.5 / 2002–2015 0.35 / ≥2016 0.24 W/(m²K). 예: B-01 2001년 벽 0.21 < 0.5 × 0.7 → 부분 개조 칸 + 모순 기록("개조 기록 없음 vs 기준보다 좋은 U값").
  **미사용 공간** (`unheated_area_note`): 점추정 면적 × 0.85, MC 범위 × 0.7~1.0 (CEO D7). 그 층 라디에이터 수는 데이터에 없으므로 개수는 그대로 두고 기사 확인 항목에 "미사용 층 라디에이터 개수·밸브 상태".
  `k`: dev 3채로 보정한 유일한 파라미터. 전날 계산 **k = 1.01** (D7·D8 반영 후), leave-one-out 오차 B-01 +20% / B-02 −9% / B-03 −8%. (당일 calibrate.py로 재계산)
* **(보조) 소비량법**: `P_cons = Q_space / 2000 h`. 판정엔 안 쓰고, 주 방식과 비교해 ±40% 넘게 다르면 모순 2b로.
* (P2) 도일법 + 지역 설계 외기온도: 뮌헨권 −16 °C, 함부르크권 −12 °C (DIN/TS 12831-1 대표값). 면적법 표는 이미 설계조건을 포함하므로 P0에선 안 씀.

**2b. 모순 점검 (규칙, engine이 판정 / LLM은 NotesObs 사실만)**
주최 측: 일부 케이스는 일부러 모순됨. 아래 규칙마다 걸리면 `contradictions`에 `{what, sources, trusted, why}` 추가 + 해당 값 MC 범위 확대.
* 소비량 부하 vs 면적·연식 부하 ±40% 초과 → 면적·연식 신뢰. 이유 후보를 NotesObs에서: 보조 열원 겨울 내내 → 소비량 과소 / 미사용 공간 → 면적 과대 / 둘 다 없으면 "사용 습관 또는 기록 오류, 기사 확인"
* `extra_source_all_winter` (장작난로 등) → 소비량 과소 확정, 소비량 기반 값은 하한으로만
* `unheated_area_note` → 난방 면적 점추정 × 0.85, 범위 × 0.7~1.0
* `renovation` 비어 있음/unrenovated인데 NotesObs에 명시적 단열 조치 또는 벽 U값 < 연식 기준 × 0.7 → 부분 개조로 취급 + 기록
* `dhw_by_boiler = yes`인데 `solar_thermal_dhw` → 온수 몫 절반
* `energy_carrier = gas`인데 detail이 LPG → 연료 lpg로 정정 기록
* 리터·kWh 둘 다 있으면 `리터 × 10`과 kWh 대조, ±15% 초과 시 기록
* `current_flow_temp_c` 있고 계산 공급온도가 10 K 넘게 높음 → 라디에이터 추정 과소 가능성, 기록
* 연식이 오래됐는데 바닥난방 → 개조 이력 가능성, 기록만
dev에서 보이는 모순: B-01 (1만 kWh vs 9.6 kW, gas/LPG), B-02 (장작난로 겨울 내내, 태양열 온수), B-03 (증축 꼭대기 층 미사용).

**3. 필요 공급온도 — 라디에이터 출력식 (DIN EN 442)**
* 바닥난방 → 35~40°C, JAZ 4.0
* 라디에이터 출력: `Φ = Φ_n × (ΔT / ΔT_n)^n`
  * `Φ_n` = 정격 출력 (75/65/20°C 기준, `ΔT_n ≈ 50 K`), `n ≈ 1.3` (라디에이터 지수)
  * `ΔT` = 대수평균 과잉온도 `(T_flow − T_return) / ln((T_flow − 20)/(T_return − 20))`
* 조건: `Σ Φ_rad(T_flow) ≥ P_load` 를 만족하는 최소 `T_flow` 를 수치로 풂 (스프레드 T_flow − T_return = 7~10 K)
* 근사(산술평균): `ΔT_need = 50 × (P_load / ΣΦ_n)^(1/1.3)`, `T_flow ≈ 20 + ΔT_need + spread/2`
* `ΣΦ_n`: 라디에이터 크기 → 아래 정격 표 × 개수 (가장 큰 불확실성 원천. 이 표가 판정을 가른다: 예시 집 8개 기준 0.8/1.5/2.5 kW면 96/69/54°C)

  | 크기 | 대표 형태 (EN 442, 75/65/20) | Φ_n 점값 | MC 범위 |
  | --- | --- | --- | --- |
  | small | Typ 11 (판 1장), 600 × ~800 | 0.7 kW | 0.5–0.9 |
  | medium | Typ 22 (판 2장), 600 × 800–1000 | 1.5 kW | 1.3–1.7 |
  | large | Typ 22 600 × 1200, 또는 Typ 33 (판 3장) 600 × 1000–1200 | 2.2 kW | 2.0–2.7 |

  출처 (75/65/20 °C, EN 442): Kermi therm-x2 Typ 22 600×800 = 1,333 W, 600×1000 = 1,666 W, 600×1200 = 1,999 W / Typ 33 600×1000 = 2,236 W, 600×1200 = 2,683 W / Buderus VC-Profil Typ 22 600×1000 = 1,688 W ([energiefluss24.de/waermepumpe/plattenheizkoerper](https://www.energiefluss24.de/waermepumpe/plattenheizkoerper), 2026-10-23 확인). **small(Typ 11)만 [estimated]**: 판 1장 ≈ Typ 22의 약 절반으로 가정. UI·피치에서 "제조사 표 기준 가정"으로 표시.
  사진에서 크기 판정 기준: 판(Platte) 개수 = 비스듬히 찍은 사진의 두께(11 ≈ 6–7 cm, 22 ≈ 10 cm, 33 ≈ 16 cm), 폭은 콘센트(≈8 cm)·창틀 기준.
  크기 모름(데이터는 전부 "type not documented") → small~large 균등 샘플(평균 ≈ medium). 개수: `radiator_info` 숫자 → 없으면 `rooms × 1.3` → 없으면 `living_area_m2 / 18` (±2). P0 점추정은 medium × 개수, `confidence` 낮음.
  dev 확인(k=1.01): 점추정(medium) B-01 54.0 °C 🟢 ✅ / B-03 58.2 °C 🟡 ✅. 몬테카를로(크기 0.25/0.5/0.25): B-01 p50 54.6 °C, 확률 🟢0.52 🟡0.20 🔴0.28 / B-03 p50 58.8 °C, 🟢0.33 🟡0.23 🔴0.44. → **3/3**, 파라미터 추가 없음.
  **판정 색 규칙 (CEO D10)**: `best_color` = 몬테카를로 **p50 공급온도의 색** (확률 최다 색이 아님 — 라디에이터 크기 분포가 한쪽으로 긴 꼬리라 최다 색은 빨강 쪽으로 쏠림, B-03이 그 예). 최대 확률 < 0.6이면 `boundary = True` → 화면에 "불확실: 🟢/🟡" 처럼 상위 두 색과 확률 표시, 방문 유형 "준비물 들고 방문". 피치: "모르면 확률로 말한다". (이전 ±1.5 °C 경계 규칙은 이걸로 대체)
* 참고: 55/45°C에선 라디에이터가 정격의 약 절반만 냄 ((30/50)^1.3 ≈ 0.52). 옛날 집은 90/70 기준 과대설계가 많아 생각보다 자주 통과
* 단관식: 뒤쪽 라디에이터 입구온도가 낮아짐 → +5~10 K 패널티 (문헌값 고정, 보정 안 함)
* **표시 클립**: 계산된 T_flow가 70°C 초과면 화면엔 ">70°C"로 표시(스케일 끝), 판정은 빨강·category=temperature. 내부 값은 Rechenweg에만.

**4. JAZ 구간**
바닥난방 → 4.0 / ≤55 → 3.5 / 55~60 → 2.8 / >60 → none

**5. 비용**
`cost_now = annual_fuel_kwh × 연료단가`
`cost_hp = Q_heat / JAZ × 0.26` (온수 포함 전체 열 기준)
`saving = cost_now − cost_hp`

**6. 신호등** (3채 기준값 보고 경계 조정)
* 🟢 바닥난방, 또는 라디에이터 ≤55°C 그대로
* 🟡 55~60°C (현장 플래그로 초록이 캡된 경우 포함)
* 🔴 >60°C ("부족분 25%" 규칙은 삭제: n=1.3·스프레드 10K에서 ≈60.5°C라 55–60 경계와 중복)
* ❔ unclear — **P0에서도** 적용: 면적·연식(부하 계산용)이나 라디에이터 개수 중 하나라도 없으면 판정 보류. **라디에이터 개수는 데이터·`rooms × 1.3`·`면적/18` 어느 것이든 있으면 "있음"**, 크기 모름은 medium + 낮은 확신도로 처리(unclear 아님). P1부터는 최대 확률 < 0.6 기준 추가. 단 unclear여도 점추정(`best_color`·온도·부하)은 정격 표 기본값으로 계산해 둔다 (Evaluation 탭·기사 브리핑용)
* **빨강 증거 기준이 초록보다 높다**: 라디에이터 정보 없이 열수요만 높으면 빨강 금지 → unclear + 라디에이터 사진 요청

**6b. 빨강/노랑 → "이러면 됨" 경로 (물리만, 금액·단열 효과 숫자 지어내지 않음)**
* 필요한 라디에이터 정격 증가량: `ΣΦ_n,needed(55°C) − ΣΦ_n` → "라디에이터 출력 약 X kW 추가"
* 또는 필요한 부하 감소율: `1 − P_load,allowed(55°C) / P_load` → "열손실이 약 Y% 줄면 노랑/초록" (어떤 단열이 몇 % 줄이는지는 말하지 않음, 기사·에너지 컨설팅으로)

**7. 불확실성**
비어 있는 인자를 사전분포에서 샘플링해 N=500 몬테카를로. 출력은 전부 p10~p90 범위 + 신호등 확률.
항상 포함하는 불확실성: 면적·연식 W/m² ±20%, 라디에이터 정격 표 범위, 모순 걸린 값은 범위 확대. 소비량 비교값엔 날씨 ±10%. 사전분포 폭은 위 정격 표 범위를 그대로 쓴다(새로 지어내지 않음). 피치에서 "범위 폭은 명시한 가정에서 나온다"고 말한다.
구현: 샘플을 numpy 배열로 한 번에 계산(샘플마다 pydantic 객체 만들지 말 것). 결과는 `st.cache_data`로 House 해시 기준 캐시.
최대 확률 < 0.6 이면 `unclear` + 다음 사진 미션.

**8. 다음 질문**
비어 있는 인자 각각에 대해: 그 인자를 고정했을 때 신호등 분포 엔트로피가 얼마나 줄어드는지 계산 → 가장 많이 줄이는 1개.

**9. 기사 방문 준비서** (`installer_brief`, CEO E1)
* **방문 유형** (규칙, **위에서부터 첫 매치**):
  0. `boundary`(최대 확률 < 0.6) → "준비물 들고 방문" (불확실은 현장에서 판단)
  1. 🔴 → "방문 보류 + 이러면 됨 경로 + 리드 보관"
  2. ❔ unclear → "준비물 들고 방문 + 사진 1장 요청"
  3. 🟡 또는 모순 있음 또는 (🟢 + 확신도 < 0.7) → "준비물 들고 방문"
  4. 🟢 + 모순 없음 + 확신도 ≥ 0.7 → "원격 견적 가능"
* **확신도·lead_score (P0)**: 색 확률은 P0 몬테카를로 값 사용. (아래 1/0/0 대체는 MC가 실패할 때만) `confidence` = 핵심 필드 5개(면적·연식·연료량·라디에이터 개수·크기)의 confidence 평균 — loader 데이터 값 0.9, 정규식 추정(rooms×1.3·면적/18) 0.5, 빈 값·크기 모름 0.3, 드롭다운 0.8 — 에서 모순 1건마다 −0.1, unclear면 **confidence = min(평균, 0.5)**, 하한 0.1. MC 실패 시 대체: `p_green/p_yellow/p_red` = best_color에 1, 나머지 0. `lead_score = (p_green + p_yellow) × confidence`
* **준비물 추정** (물리만, 금액 없음):
  * 교체 후보 라디에이터 수 ≈ `ceil(ΣΦ_n 부족분(55°C 기준) / (large 점값 2.2 − 현재 크기 점값))`. 크기 모름 → medium(1.5). **부족분 ≤ 0이면 "교체 0개"**, **현재 크기가 large인데 부족하면 "교체로는 부족 → 라디에이터 추가 또는 방별 확인"** (0으로 나누기 방지). **바닥난방이면 "해당 없음"**(바닥난방에 딸린 라디에이터 1~2개는 "확인만"). 범위: P0는 점값 ±1, P1부터 p10–p90. 예: "약 3개 (2–4) Typ 33급으로"
  * 데이터의 밸브 교체 수 그대로 (예: B-03 "12 valves")
  * 수력 밸런싱(hydraulischer Abgleich): `hydraulic_balanced`가 True(데이터 "balanced", "already preset")면 "확인만", 아니면 "필요"
* **현장 확인 항목**: 2b 모순마다 "현장에서 X 확인" 한 줄 + site_flags + 단관/복관 unknown이면 배관 확인
* 항상: 실외기 위치·소음 거리, 전기 인입 용량, 수력 밸런싱
* 불확실했던 인자: "거실 라디에이터 출력 부족 의심", "단관식 가능성 높음 → 배관 확인" 등
* 신호등 이유와 예상 범위 요약

## 입력 설계 (`schema.py`)

원칙: 형식 안 가리기 / 사진 한 장으로 필드 여러 개 / 정보가치 낮은 건 묻지 말고 사전분포로.
각 필드에 `effort` 점수(1~3). 다음 질문 = 엔트로피 감소량 ÷ effort 최대.

**드롭다운 (사진 없이 30초)**: 건물 유형, 대략 년식, 면적, 거주 인원, 연료, 바닥난방 여부, 라디에이터 개수, 창문 교체 여부, 문화재 여부, 월 선납금(Abschlag, 선택)
라디에이터 크기 드롭다운은 작음/중간/큼 **그림 선택**으로.

**핵심 사진 3장** — `merge` 출처 우선순위 (LLM이 매긴 confidence는 보정 안 된 값이라 출처를 이기지 못함):
`fuel_type`·연료량: bill > dropdown / `radiator_*`·`pipe_system`: photo > dropdown / `build_year`·`living_area_m2`·`occupants`: dropdown > photo / 나머지: photo > dropdown > prior. 같은 출처끼리만 confidence 높은 쪽

1. 외관 — "Ganzes Haus von der Straße fotografieren, mit Dach und etwas Umgebung"
   → `building_type`, `build_year`(범위), `windows`, 외단열 흔적, 지붕 상태, 실외기 자리 힌트, 문화재 느낌
2. 고지서 — "Heizkostenabrechnung in beliebiger Form: Foto, PDF oder Screenshot aus der App"
   → `fuel_type`, `BillObs` 원본 숫자(kWh·m³·상태수·발열량·리터 중 보이는 것), 청구기간. 환산·365일 보정은 engine
3. 거실 라디에이터 — "Größter Heizkörper im Wohnzimmer, schräg von der Seite, mit den Rohren darunter"
   → `radiator_type`(비스듬히 찍어야 판 개수 보임), 크기(콘센트·창틀 기준, A4는 선택), `pipe_system`, 밸브·온도조절기

**선택 사진 (엔진이 요청할 때만)**

4. 바닥난방 분배기 → `heat_distribution` 확정, 회로 수
5. 보일러 앞면 전체 (명판 말고) → `boiler_condensing`(플라스틱 배기관·응축수 배수관), 연식, 디스플레이 공급온도
6. 실외기 후보 위치 → `outdoor_unit_space` (소음 거리 확정은 기사 체크리스트)

**재촬영 루프 (P2 — CEO R1, 시간 남을 때만)**

* 각 사진 미션에 **예시 이미지**(어디를 어떻게 찍는지) 표시
* 추출 시 필드마다 null이면 `missing_reason` 반환: `not_visible` | `blurry` | `ambiguous` | `wrong_object`
  → LLM은 이유 코드만 냄 (판정 아님). 문구는 app.py가 매핑: 예) `pipe_system`+`not_visible` → "Die Rohre unter dem Heizkörper sind nicht im Bild. Bitte etwas tiefer fotografieren."
* **부분 수용**: 크기는 나오고 배관만 안 보이면 크기는 저장, 배관만 다시 요청
* **재시도 최대 2회** → 그래도 null이면 드롭다운/사전분포로 대체하고 기사 체크리스트에 추가. 무한루프 금지
* 데모: 일부러 배관 안 나온 사진 먼저 → 구체적 재촬영 안내 → 좋은 사진 → 범위 좁아짐 (캐시로 준비)

## 화면 (`app.py`)

* 🏠 Homeowner (**P0-d**): 드롭다운 입력 → 신호등(경계면 두 색) + 이유 → 공급온도 스케일 → 비용 → "이 정보가 있으면 더 정확해요" 1개(P0는 고정 규칙: 비어 있는 필드 중 라디에이터 크기 > 연료량 > 연식 순). **P1**: `st.file_uploader`(폰 후면 카메라 — 라이브 촬영은 이걸로) + `st.camera_input`(노트북) → 추출 결과(신뢰도) → 사진 추가할 때마다 범위가 좁아지게
* 🔧 Installer (**P0-b**): 건물 선택 → **방문 준비서 한 장**: 방문 유형 배지, 준비물 목록(교체 후보 라디에이터 수·밸브·밸런싱), 현장 확인 항목(모순·site_flags·배관), 필요 공급온도·부하 점값(범위는 P1부터), 빈 칸 목록
* 📊 Evaluation: 5채 로드 → 3채는 기준값과 나란히 비교, 2채는 결과만. **피치에서 이 화면 사용**
* 사이드바 Demo mode 토글 (**P1**, 사진 흐름과 함께): 켜면 LLM 대신 `samples/cached_extract.json`. P0는 LLM 없이 돌아가므로 토글 불필요

## 작업 방식 (에이전트 운용)

* **Claude 세션은 1개.** 순서대로 schema → loader → engine → calibrate → app(Evaluation) → engine.installer_brief + app(Installer) → app(Homeowner 드롭다운) → (P1) extract → app(Homeowner 사진). 팀원이 합류하면 그때 git worktree로 레인을 나눈다(같은 폴더에서 두 세션 금지)
* **`/check` 통과할 때마다 커밋** (변경된 파일만 이름으로 `git add`, `-A` 금지). 터지면 마지막 커밋으로 롤백. 커밋 없이 30분 넘게 작업 금지
* P0-a 끝, P0-b 끝, 코드 동결 직전에 **`/hp-review`** (작업 안 본 별도 에이전트 검수)
* 현장 정보는 전부 **`/intake`** 로 받는다
* 슬래시 커맨드: `.claude/commands/` 의 `intake`, `check`, `hp-review` (gstack `/review`와 이름 겹치지 않게)

## 코딩 규칙

* 기존 함수 시그니처 유지. 필요하면 새 함수 추가.
* LLM 호출·파일 입력은 전부 try/except. 실패 시 캐시로 대체하고 화면에 작게 표시.
* **Streamlit은 클릭마다 스크립트 전체를 다시 돈다** → `extract()`는 `st.cache_data`로 `(sha256(file_bytes), mission)` 기준 캐시, 누적 House는 `st.session_state`에 저장. 같은 사진으로 API를 두 번 부르지 않는다. "결정론" 장면은 같은 House → `evaluate_mc` 두 번으로 보여준다(LLM 추출은 결정론 아님).
* 고지서는 PDF도 받음(API 문서 입력). 원본·이름·주소는 저장하지 않고 추출한 숫자만 세션에 유지.
* UI에 Key terms 4개(Heizlast, Vorlauftemperatur, JAZ, Ein-/Zweirohr)가 결과와 함께 보이게, ⓘ 툴팁으로 설명.
* 한 번에 한 기능만 수정. 수정 후 `streamlit run app.py`로 해피패스 확인.
* 설명은 짧게. 바로 코드.

## 데모 해피패스

(페르소나: 1972년 연립주택 140m², **부분 개조(창문 교체·지붕 단열)**, 3인, 가스 18,000 kWh)
(전날 계산, 면적·연식법 80 W/m² × k 0.98 → 11.0 kW: 라디에이터 중간(1.5)×8 → 70.7°C 🔴 / 큼(2.2)×8 → 58.8°C 🟡 (60 경계 ±1.5 안 → "경계 🟡/🔴"). 큼 × 9개 → 55.8°C "경계 🟢/🟡". 페르소나는 어느 쪽이든 경계에 걸림 → 데모에선 "경계라고 말하는 장면"으로 쓴다. 보정 후 다시 확인)
**P0만으로 되는 순서 (기본, CEO D5)**: 📊 Evaluation 탭 — 3채 오차·LOO → 평가 2채 결과 → B-01 모순 잡기 →
🔧 Installer 탭 — B-03 방문 준비서 (준비물 들고 방문, 라디에이터 약 N개, 밸브 12개, 증축층 확인) →
🏠 Homeowner — 페르소나를 드롭다운으로 입력 → 신호등·이유·공급온도 스케일·비용 (라디에이터 크기 "큼" 선택 시 🟡)
**P1이 되면 Homeowner 부분을 교체**: 드롭다운 → ❔ unclear → "고지서 아무 형식으로" → 앱 스크린샷 → kWh 추출·비용 → "거실 라디에이터 비스듬히 + 배관" → 라디에이터 사진 → 🟡 + 공급온도 밴드 좁아짐
(P2 재촬영 루프는 시간 남을 때만. 전부 캐시로 리허설)

## "돌아간다" 증명 장면 (데모에 반드시 포함)

1. **정확도**: Evaluation 탭 — 3채 오차, leave-one-out, 평가 2채 결과
2. **지어내지 않음** (P1): 엉뚱한 사진(고양이 등) → `wrong_object`, 값 null, 판정 안 바뀜
3. **모르면 모른다고 함**: P0 — Homeowner에서 연식을 비우면 ❔ unclear + "이 정보가 있으면 더 정확해요" 1개 / 경계 집(B-01)은 "경계 🟢/🟡". P1 — 엔트로피 기반 사진 하나 요청
4. **기사 준비서**: 🔧 Installer 탭에서 B-03 → "준비물 들고 방문: 라디에이터 약 N개, 밸브 12개, 밸런싱, 증축층 난방 여부 확인" (재촬영 루프는 P2, 시간 남을 때만)
4b. **AI가 메모를 읽음**: Evaluation 탭에서 각 집의 "AI가 찾은 사실 + 원문 인용" (예: B-02 "A wood stove is used all winter" → 보조 열원, 겨울 내내)
5. **근거 추적**: Rechenweg 펼쳐서 숫자 체인 보여주기
5b. **모순 잡기**: Evaluation 탭에서 B-01 → "고지서 기반 3.0 kW vs 면적·연식 11.5 kW (−74%, ±40% 규칙) → 면적 기반을 믿음, 원인 후보: 사용 습관·LPG, 기사 확인" / B-02 → "장작난로 겨울 내내 → 소비량은 하한으로만" (B-02는 −31%라 ±40% 규칙이 아니라 장작난로 규칙으로 잡힘). 주최 측이 심은 모순을 우리가 찾았다는 장면
6. **결정론**: 같은 입력 두 번 → 같은 결과 (P0 `evaluate`는 원래 결정론, P1 `evaluate_mc`는 seed 고정)
7. **라이브 한 방(선택)**: 발표장 라디에이터를 폰으로 즉석 촬영. 실패하면 Demo mode 캐시로 즉시 전환
* 백업: 해피패스 화면 녹화 영상 준비 (와이파이 사망 대비, 발표는 라이브 우선)

## 피치 핵심 문장

* "In Germany, the scarcest resource isn't energy. It's the installer's time."
* "The LLM reads. Physics decides. Nothing is made up."
* "We only ask for the one photo that actually changes the answer."
* "We don't cancel site visits. We make them short and precise."
* "Real data contradicts itself. We don't hide it — we show which source we trusted and why."
* 로드맵 Phase 2: nuuEnergy 실제 방문 데이터로 보정 파라미터·기사 체크리스트를 학습 (kNN/유사도는 여기서)

## 하지 말 것

* 로그인, DB 서버, 테스트 코드, 리팩터링
* LLM이 신호등·판정·숫자를 직접 내게 하는 것
* 고정 가정 외의 단가·설치비·보조금 숫자 출력
* 가짜 방문 DB 생성
* 마지막 1시간에 새 기능 추가 (코드 동결)

---

## 현장 정보 반영 프로토콜 (에이전트는 새 정보가 붙여넣어지면 반드시 이 순서로)

사용자(준우)는 도메인·통계 배경 없이 현장에서 받은 걸 그대로 붙여넣는다 (브리핑 텍스트, 스크린샷, 데이터 파일, 멘토·심사위원 말, 규칙 공지).
에이전트가 해석하고 계획을 맞춘다. 사용자에게 해석을 떠넘기지 않는다.

1. **분류**: 이 정보가 건드리는 층을 고른다 — 산출물/심사 · 데이터 형식 · 기준값 · 도메인 사실 · 제약(시간·팀·규칙) · 피드백
2. **3줄 요약**: 뭐가 새로 생겼는지, 쉬운 말로
3. **충돌 점검**: CLAUDE.md의 어느 섹션과 부딪히는지 섹션명으로 나열. 없으면 "충돌 없음"
4. **최소 수정 제안**: 바꿀 줄만. 핵심 원칙 1~7은 새 정보가 명시적으로 요구할 때만 건드림
5. **우선순위 영향**: P0/P1/P2/타임라인 중 바뀌는 게 있으면 명시. 시간이 줄면 P2 → P1 순으로 자름
6. **반영 후 기록**: 아래 `결정 로그`에 한 줄 추가, `열린 질문`에서 닫힌 것 체크
7. 사용자가 이해 못 했을 법한 용어가 나오면 아래 `도메인 배경`의 해당 항목을 한 줄로 같이 설명

### 상황별 플레이북

**데이터 파일(CSV/JSON)이 들어오면**
* 컬럼/키 전부 출력 → `House` 필드와 매핑표 작성 → `schema.py` 필드명 맞춤 (코드 쪽을 데이터에 맞춘다)
* 기준값 필드 확인 후 보정 대상 결정:
  * 난방부하(kW) 있음 → 면적·연식법의 k 1개 보정 (dev 데이터로 확정됨)
  * 공급온도 있음 → 라디에이터 룩업 스케일 / 단관 패널티 보정
  * 신호등만 있음 → 색 경계(55/60)는 챌린지 표라 고정, 라디에이터 표 스케일 1개만 맞춤
  * 비용·JAZ 있음 → 우리 비용식이 고정 가정대로 같은 값을 내는지 검증 (다르면 그들의 식을 따름)
* 위치(주소·PLZ·도시) 있음 → `T_NA`, `G` 상수 결정. 없으면 바이에른 대표값 + 범위
* 연료가 기름 → 리터 × 10 kWh 확인
* 사진이 데이터에 포함 → extract 경로로 2채도 돌려보고, 데이터 값과 비교해 추출 정확도 표시
* 우리 스키마에 없는 필드 → 결과에 영향 큰지 판단해 추가, 아니면 무시하고 로그에 기록

**심사·규칙 공지가 들어오면**
* `심사 기준` 표와 `산출물` 줄 갱신. 시간 변경이면 `타임라인` 재배분
* "코드는 행사 중 작성" 류 규칙 → 미리 만든 코드 범위를 사용자에게 알리고 지시 대기

**멘토·nuuEnergy 직원 말이 들어오면**
* 도메인 사실(예: "우리는 공급온도를 이렇게 정의한다") → 엔진·측도 정의 우선 반영
* 선호(예: "기사 화면이 더 중요") → 우선순위만 조정, 원칙은 유지

**사용자가 사진/스크린샷만 던지면**
* 텍스트를 읽어서 위 분류부터. 읽을 수 없는 부분은 추측하지 말고 무엇이 안 보이는지 말함

### 열린 질문 (닫히면 체크)

- [ ] **제출 마감 시간·발표 순서** (→ 타임라인 역산 규칙)
- [x] 데이터 사용 조건 — 익명화된 데이터라 비공개 리포 커밋 OK로 판단 (현장에서 한 번 더 확인)
- [x] 기준값 형식 — `reference_heating_load_kw` + `expected_verdict` (green/yellow/red)
- [x] CSV 필드명 — 매핑표 참고 (JSON 형식은 당일 확인)
- [x] 건물 위치 — 지역 단위 (Munich 82xxx, Hamburg 21xxx)
- [x] 평가 2채에 사진 포함 여부 — 없음 (데이터 설명상 사진 없음)
- [ ] **nuuEnergy 기준 부하는 어떻게 계산했나?** (면적·연식 경험값 / U값 기반 DIN 12831 / 소비량) → 멘토에게 첫 질문. 답에 따라 k와 표 재검토
- [ ] 팀 규모·역할
- [ ] 사전 코드 작성 허용 여부

### 결정 로그 (형식: `HH:MM 무엇을 왜 바꿈`)

- (시작 전) kNN+가짜 DB → 물리 엔진. 이유: 심사가 실제 2채 기준값 대비 정확도, synthetic DB는 방어 불가
- (전날 CEO review 4차, 외부 검토 반영) D8 벽 U값 < 연식 기준×0.7 → 부분 개조(B-01), k=1.01, dev 3/3 / D9 LLM 메모 읽기 P0 핵심(캐시) / D10 간단 몬테카를로 P0, best_color = p50 색, 최대 확률 < 0.6 → 불확실 표시(±1.5 °C 규칙 대체) / D11 일괄 업로드 P2로, 평가 표에 lead_score 열만
- (전날 CEO review 3차) D7 미사용 공간 면적 × 0.85 반영, k 0.93 → 0.98, 경계 ±1.5 °C 규칙(두 색 표시 + 준비물 방문). dev 두 집이 경계에 붙어 어떤 1-파라미터 보정도 점추정 색 2/3 — 과적합 대신 경계 표시. 스펙 리뷰 2차 반영(best_color·boundary 필드, confidence 값 출처, 바닥난방/large 부족 준비물, U값만으로 개조 판정 안 함, preset≠balanced, 증명 장면 P0/P1 구분, Homeowner P0는 드롭다운)
- (전날 CEO review 2차) D5 사진 흐름 P0-b → P1, 순서 P0-a 채점 → P0-b Installer → P0-c 일괄 → P0-d Homeowner 드롭다운. D6 일괄 분류는 LLM 0회(규칙·키워드). 스펙 리뷰 반영: 방문 유형 우선순위·unclear 처리, P0 확신도/lead_score 정의, 준비물 0 나누기 방지, valves_to_replace·hydraulic_balanced 필드, 데모 5b를 B-01로
- (전날 CEO review, SELECTIVE EXPANSION) E1 기사 방문 준비서 P0-b+로 추가(nuuEnergy는 자체 기사팀 설치사 → 방문 준비가 직접 가치), E2 리드 일괄 분류표 추가(확장성 15점을 화면으로), R1 재촬영 루프 P1→P2(데이터에 사진 없음)
- (전날 dev 데이터 intake) 난방부하 주 방식을 소비량/t_vbh → 면적·연식 경험값 × k로 변경. 이유: dev 3채 t_vbh가 625–2,400 h로 벌어져 1개 파라미터 보정 불가, 면적법은 k=0.93에서 LOO ±20%. 모순 점검(2b) 추가(주최 측 "일부러 모순"), CSV 텍스트 파싱을 P0-a로, 사진 흐름은 P0-b 보너스로. 연료 lpg/district/electric 추가(district·electric 현재 비용은 단가 미제공 표시)
- (전날 eng review) 라디에이터 정격 표·Hs 기준 η·게이트=기사 확인·25% 규칙 삭제·보정 1개·T_flow 클립·날씨 ±10% / 고지서는 원본 숫자만 추출·미션별 스키마·출처 우선 merge·추출 캐시·사진 리사이즈·평가 탭 점추정 항상 표시 / 세션 1개·/check는 변경 파일만 커밋·/review→/hp-review / 마감 역산·전날 Cloud 배포

---

## 도메인 배경 (사람·에이전트 공용 입문서)

**히트펌프**: 열을 만드는 게 아니라 바깥 공기에서 옮겨옴. 전기 1 kWh → 열 3~4 kWh. 이 연간 평균 비율이 **JAZ**.

**왜 공급온도(Vorlauftemperatur)가 전부인가**: 히트펌프는 물을 덜 뜨겁게 데울수록 효율이 높음. 바깥 공기와 목표 물 온도 차이가 클수록 압축기가 더 일해야 해서. 그래서 "우리 집 되냐" = "미지근한 물로도 집이 따뜻하냐".

**55 / 60°C의 의미**: 챌린지 JAZ 표의 구간 경계. ≤55 → JAZ 3.5, 55~60 → 2.8, 표가 60에서 끝남 → 그 위는 이 챌린지 가정으로는 권장 불가. 우리가 정한 숫자가 아님.

**필요 공급온도의 정의**: 그 지역 설계 외기온도(가장 추운 날 기준값)에서 기존 라디에이터로 실내 20°C를 유지하는 데 필요한 물 온도. 한겨울 최악 조건 기준이라는 게 핵심.

**난방부하(Heizlast)**: 그 최악의 날에 집이 잃는 열(kW). 우리는 측정 못 하니까 연간 연료 소비량에서 역산. 이게 "추정"의 정체.

**추정 체인과 가정** (각 화살표마다 가정이 하나씩 끼어 있음 = 불확실성의 출처)
`면적 × 연식별 W/m² × k` → `난방부하 kW` (교차 확인: `고지서 kWh` →η→ `열` →온수 차감→ `÷2000 h`) →(라디에이터 총출력)→ `필요 공급온도` →(JAZ 표)→ `신호등`, 그리고 `고지서 kWh`·`JAZ` → `비용`. 두 부하가 크게 다르면 그게 "모순" 신호.
가장 큰 불확실성: 라디에이터 총출력 > 난방부하 방법 > 온수 > 효율.

**라디에이터 출력식**: 라디에이터는 물이 식으면 열을 덜 냄. 정격(75°C 물 기준)의 출력이 55°C 물에선 약 절반. 옛날 집은 원래 90°C 기준으로 라디에이터를 크게 달아놔서, 낮은 온도에서도 버티는 경우가 많음 → "생각보다 많은 집이 된다".

**단관식 / 복관식 (Ein-/Zweirohrheizung)**: 복관은 각 라디에이터에 뜨거운 물이 따로 들어감. 단관은 한 줄 파이프에 라디에이터가 줄줄이 달려서, 뒤쪽일수록 식은 물을 받음 → 공급온도를 더 높여야 함 → 히트펌프에 불리. 60~70년대 건물에 흔함.

**몬테카를로**: 모르는 값(예: 라디에이터 총출력)에 숫자 하나를 찍지 않고, 그럴듯한 범위에서 500번 랜덤으로 뽑아 엔진을 500번 돌림. 결과 분포 → 범위(p10~p90)와 색 확률. 엔진은 그대로, 반복문으로 감쌀 뿐. "다음 질문"은 각 미지 값을 안다고 치고 다시 돌렸을 때 결과가 가장 선명해지는 걸 고름.

**보정(calibration)**: 3채 = 학습셋, 2채 = 테스트셋. 3채에서 엔진 값과 nuuEnergy 기준값을 비교해 상수 1개만 조정. 점 3개로 많이 맞추면 과적합 → 2채에서 터짐.

**기사(Heizungsbauer) 현장 방문 흐름** (일반적인 흐름, nuuEnergy 실제 프로세스는 현장에서 확인)
1. 기존 난방 확인: 보일러 종류·연식, 소비량, 공급온도 설정
2. 방별 확인: 면적, 라디에이터 종류·치수 → 방별 난방부하(DIN EN 12831) vs 라디에이터 출력 비교 → 교체할 라디에이터 결정
3. 배관: 단관/복관, 배관 상태, 수력 밸런싱(hydraulischer Abgleich) 필요 여부
4. 실외기 위치: 설치 공간, 이웃까지 소음 거리
5. 실내: 온수 탱크·버퍼 탱크 놓을 자리
6. 전기: 분전반·인입 용량, 계량기
7. 견적 → 보조금 신청 → 설치 → 밸런싱·시운전

**우리 툴이 미리 채우는 것**: 1(소비량·보일러 대략), 2의 전체 합 수준(어느 방인지는 못 함), 3의 단관/복관 추정
**못 채우는 것 = 기사 브리핑으로 넘기는 것**: 2의 방별 판정, 3의 밸런싱, 4·5·6 전부

**신호등의 실무적 의미**: 🟢 짧은 방문/원격 견적 · 🟡 브리핑 들고 방문(라디에이터 교체 같이 판매) · 🔴 방문 보류 + "이러면 됨" 경로 + 리드 보관 · ❔ 사진 하나 더
