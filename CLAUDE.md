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
* 데이터: 실제 건물 5채(CSV + JSON). 3채는 nuuEnergy 기준값 있음(보정용), 2채는 기준값 숨김(심사용).
* 코드 품질·테스트 신경 안 씀. 데모가 안 터지는 것만 중요.

## 심사 기준 → 우리가 점수 따는 곳

| 기준 | 점수 | 우리 무기 |
| --- | --- | --- |
| Technical execution & reliability | 25 | Cloud 배포 + Demo mode 캐시 + JSON 경로로 사진 없이도 2채 돌아감 |
| Problem-solution fit & user value | 25 | 3분, 집주인 한 문장 이유, 비용 범위, 기사 브리핑 |
| Explainability & handling uncertainty | 20 | 모든 출력이 범위 + 신호등 확률, `unclear` 허용, "기사가 X·Y 확인" |
| Innovation & smart use of technology | 15 | LLM=센서 / 물리=판정 분리, 엔트로피 기반 "사진 하나만" |
| Feasibility & scalability | 15 | API 1~2회 호출, 고정 가정 교체만으로 확장, Phase 2 실방문 데이터 보정 |

심사 측 명시: "모르겠다, 기사가 X·Y 확인해야 함"이 자신 있게 틀린 숫자보다 낫다 → `unclear`는 실패가 아니라 기능.
Key terms에 Heizlast(가장 추운 날 필요 kW), Vorlauftemperatur, JAZ, 단관/복관이 명시됨 → 출력에 이 네 개가 반드시 보이게.

## 우선순위 (이 순서대로만 만든다. 위가 안 돌면 아래 손대지 않음)

* **P0-a 채점 경로**: `loader.py` → `engine.py`(산술 근사식, JAZ 구간, 비용, 신호등, 이유) → `calibrate.py` → 📊 Evaluation 탭
  * Evaluation 탭: 3채 기준값 vs 우리 값(오차 %) + **leave-one-out**(2채로 보정 → 나머지 1채 예측, 3번 반복) + 평가 2채 결과(범위 포함)
  * 모든 결과에 **`Rechenweg` expander**: 고지서 kWh → 실제 열 → 난방열 → 난방부하 → 필요 공급온도 → JAZ → 비용, 각 단계 숫자와 쓴 가정
* **P0-b 데모 경로**: 드롭다운 + 고지서 사진 + 라디에이터 사진 추출 → 🏠 Homeowner(신호등·이유·비용·기사 체크리스트·**공급온도 스케일**) + Demo mode 캐시 + Cloud 배포
  * 공급온도 스케일: 가로 막대 35→70°C, 구간 색(바닥난방·≤55 초록 / 55–60 노랑 / >60 빨강), 우리 추정값에 마커. 판정은 3색 그대로, 스케일은 보조
* **P1**: 몬테카를로 범위·확률 → 스케일 마커를 **p10–p90 밴드**로 교체 + 색 확률 표시 → 다음 질문(엔트로피 ÷ effort) → 재촬영 루프(`missing_reason`)
* **P2**: 🔧 Installer 탭 꾸미기, 외관 사진, 도일법 병행, 대수평균 수치해, 선택 사진 4~6
* **컷**: PLZ별 설계온도/도일 조회(상수 하나로), 세밀한 라디에이터 룩업(작/중/대 3단계로)

## 타임라인 (10h)

| 시간 | 할 일 |
| --- | --- |
| 0:00–0:30 | 데이터 열어보고 스키마 필드명·기준값 형식 맞추기 |
| 0:30–3:00 | P0-a: loader + engine + calibrate + Evaluation 탭 → **여기서 2채 결과 확보** |
| 3:00–6:00 | P0-b: 추출 + Homeowner 탭 |
| 6:00–7:30 | P1 |
| 7:30–8:30 | Cloud 배포, 데모 캐시 고정, 해피패스 3회 리허설 |
| 8:30 | **코드 동결** |
| 8:30–10:00 | 피치 준비·리허설 |

## 스택

* Python, Streamlit, Pydantic, pandas, numpy, Anthropic API
* 모델: `claude-sonnet-5-5` (비전 + 구조화 출력)
* API 키: `st.secrets["ANTHROPIC_API_KEY"]` 우선, 없으면 환경변수. 하드코딩 금지.
* 배포: Streamlit Community Cloud에 미리 올려둔다 (로컬 백업 유지).

## 파일 구조 (이 외에 새 파일 만들지 말 것)

* `schema.py`    – Pydantic: `House`(입력), `Result`(출력), 고정 가정 상수, 인자→사진 미션 문구
* `extract.py`   – 사진/고지서 → `House` 부분 채움 + confidence. tool use에 `House.model_json_schema()`로 구조화 출력 강제
* `loader.py`    – 제공된 CSV/JSON → `House` (심사용 경로. 사진 없이 돌아야 함)
* `engine.py`    – 게이트, 물리 계산, 몬테카를로, 신호등, 다음 질문, 기사 브리핑
* `calibrate.py` – 3채 기준값과 엔진 출력 비교, 보정 파라미터 조정 (한 번 돌리고 값만 engine에 박음). **과적합 주의: 점 3개 → 파라미터 1~2개만 보정**(난방부하 방법/t_vbh 우선). 나머지는 문헌 기본값 고정
* `app.py`       – Streamlit. 탭 3개: `🏠 Homeowner` / `🔧 Installer` / `📊 Evaluation`
* `requirements.txt`, `.gitignore` – 이미 있음. 패키지 추가 시 requirements.txt에도 추가
* `.claude/commands/` – 슬래시 커맨드 `intake`, `check`, `review` (아래 작업 방식 참고)
* `.streamlit/secrets.toml` – 로컬 API 키 (gitignore됨, 커밋 금지). Cloud에선 앱 설정의 Secrets에 입력
* `data/`        – 제공된 5채 원본
* `samples/`     – 데모용 사진·고지서, 캐시된 추출 결과 `samples/cached_extract.json`

## 인터페이스 계약 (함수 시그니처 고정. 이것만 지키면 엔진·UI를 병렬로 만들 수 있음)

```python
# schema.py
class House(BaseModel):
    # 값 필드는 아래 스키마 초안대로, 전부 Optional
    confidence: dict[str, float] = {}      # 필드명 → 0~1
    source: dict[str, str] = {}            # 필드명 → dropdown | photo | bill | data | prior
    missing: dict[str, str] = {}           # 필드명 → not_visible | blurry | ambiguous | wrong_object
class Params(BaseModel): ...               # η, 온수, t_vbh, 단관 패널티 등 보정 대상 상수
class Step(BaseModel): label: str; value: str; assumption: str | None
class Result(BaseModel): ...               # 아래 Result 초안 + trace: list[Step] (Rechenweg)

# loader.py
def load_buildings(path="data/") -> list[tuple[str, House, dict | None]]   # (id, House, 기준값 or None)

# extract.py
def extract(file_bytes: bytes, mime: str, mission: str) -> House           # 부분 채움 + missing
def merge(base: House, new: House) -> House                                # confidence 높은 쪽 우선

# engine.py
def evaluate(h: House, p: Params = DEFAULT) -> Result                      # P0 점추정
def evaluate_mc(h: House, p: Params = DEFAULT, n=500, seed=0) -> Result    # P1, seed 고정 = 결정론
def next_question(h: House) -> str | None                                  # 다음에 물을 필드명
def installer_brief(h: House, r: Result) -> list[str]

# calibrate.py
def fit(buildings) -> Params
def leave_one_out(buildings) -> pd.DataFrame
```

`python engine.py` 단독 실행 시: 예시 집(1972 연립 140m², 가스 25,000 kWh, 3인, 라디에이터 중간 8개)으로 evaluate 결과와 Rechenweg 출력 (스모크 체크용).

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

`House` (전부 Optional, 각 필드에 confidence):

* `fuel_type` (gas | oil)
* `annual_fuel_kwh` (float) – 고지서. 기름은 리터 × 10
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
* `radiator_count` (int) – 드롭다운
* `windows` (original | double_renovated | triple)
* `roof_insulated`, `walls_insulated` (bool)
* 현장 플래그: `listed_building`, `outdoor_unit_space`, `flat_level_gas_heating` (bool)

`Result`:

* `traffic_light` (green | yellow | red | unclear) + `reason`(집주인용 한 문장) + `reason_category` (temperature | site | insulation_first)
* `p_green`, `p_yellow`, `p_red` (몬테카를로 비율)
* `required_flow_temp_c` (p10~p90 범위)
* `heat_load_kw` (범위)
* `jaz_bucket` (4.0 | 3.5 | 2.8 | none)
* `cost_now_eur`, `cost_hp_eur`, `saving_eur` (범위)
* `next_photo` (집주인 미션 1개)
* `installer_checklist` (기사 현장 확인 리스트)

## 엔진 로직 (`engine.py`)

**0. 게이트 (규칙)**
`listed_building`, `outdoor_unit_space == False`, `flat_level_gas_heating` 중 확정된 게 있으면 → 빨강, category=site. 모르면 판정 안 막고 기사 체크리스트로.

**1. 연료 → 열**
고지서 없고 선납금만 있으면: `annual_fuel_kwh ≈ monthly_advance_eur × 12 / 연료단가`, 범위 넓게(기본요금·실제 단가 차이로 −30%~+10%), confidence 낮게.
`Q_heat = annual_fuel_kwh × η` (η 기본: 콘덴싱 0.95 / 비콘덴싱 0.85 / 모름 0.9 — 보정 대상)
`Q_space = Q_heat − Q_dhw` (dhw_by_boiler면 `Q_dhw ≈ 600 kWh × occupants` 또는 `12.5 kWh/m²` — 보정 대상)

**판정 측도 정의 (피치·UI에 명시)**
"필요 공급온도" = **설계 외기온도(Normaußentemperatur, DIN/TS 12831-1, 지역별)일 때, 기존 라디에이터로 실내 20°C를 유지하는 데 필요한 공급수 온도** (= Auslegungsvorlauftemperatur).
55/60°C 경계는 우리가 정한 게 아니라 챌린지 JAZ 표의 구간. 표가 60°C에서 끝나므로 >60은 "고정 가정 밖 → 조치 필요".

**2. 난방부하 (Heizlast) — 소비량 기반 추정**
두 방법을 다 계산하고, 3채 기준값에 맞는 쪽/보정계수를 채택:
* (A) 도일법: `H [W/K] = Q_space / (G × 24)`, `P_load = H × (20 − T_NA)`
  `G` = 난방도일(Gradtagzahl, VDI 3807 계열, 지역·연도별), `T_NA` = 설계 외기온도
* (B) 풀부하시간법: `P_load = Q_space / t_vbh` (t_vbh 기본 2000 h)
* 주의: 두 방법이 20% 정도 차이 날 수 있고, 그 차이로 색이 바뀔 수 있음 → 보정 필수, 결과는 범위로
사양값 체크: `Q_space / living_area_m2`가 년식 대비 말이 되는지 (안 되면 confidence ↓)

**3. 필요 공급온도 — 라디에이터 출력식 (DIN EN 442)**
* 바닥난방 → 35~40°C, JAZ 4.0
* 라디에이터 출력: `Φ = Φ_n × (ΔT / ΔT_n)^n`
  * `Φ_n` = 정격 출력 (75/65/20°C 기준, `ΔT_n ≈ 50 K`), `n ≈ 1.3` (라디에이터 지수)
  * `ΔT` = 대수평균 과잉온도 `(T_flow − T_return) / ln((T_flow − 20)/(T_return − 20))`
* 조건: `Σ Φ_rad(T_flow) ≥ P_load` 를 만족하는 최소 `T_flow` 를 수치로 풂 (스프레드 T_flow − T_return = 7~10 K)
* 근사(산술평균): `ΔT_need = 50 × (P_load / ΣΦ_n)^(1/1.3)`, `T_flow ≈ 20 + ΔT_need + spread/2`
* `ΣΦ_n`: 라디에이터 타입·치수 → 룩업 테이블 × 개수. 모르면 년식 기반 사전분포 (가장 큰 불확실성 원천)
* 참고: 55/45°C에선 라디에이터가 정격의 약 절반만 냄 ((30/50)^1.3 ≈ 0.52). 옛날 집은 90/70 기준 과대설계가 많아 생각보다 자주 통과
* 단관식: 뒤쪽 라디에이터 입구온도가 낮아짐 → +5~10 K 패널티 (보정 대상)

**4. JAZ 구간**
바닥난방 → 4.0 / ≤55 → 3.5 / 55~60 → 2.8 / >60 → none

**5. 비용**
`cost_now = annual_fuel_kwh × 연료단가`
`cost_hp = Q_heat / JAZ × 0.26` (온수 포함 전체 열 기준)
`saving = cost_now − cost_hp`

**6. 신호등** (3채 기준값 보고 경계 조정)
* 🟢 바닥난방, 또는 라디에이터 ≤55°C 그대로
* 🟡 55~60°C, 또는 라디에이터 부족분(≤55 달성에 필요한 ΣΦ_n − 현재)이 현재의 ~25% 이하 (= 1~2개 교체 수준)
* 🔴 >60°C, 또는 게이트 차단
* ❔ unclear — **P0에서도** 적용: 연간 연료량(고지서/선납금)이나 라디에이터 정보(사진/드롭다운) 중 하나라도 없으면 판정 보류. P1부터는 최대 확률 < 0.6 기준 추가
* **빨강 증거 기준이 초록보다 높다**: 라디에이터 정보 없이 열수요만 높으면 빨강 금지 → unclear + 라디에이터 사진 요청

**6b. 빨강/노랑 → "이러면 됨" 경로 (물리만, 금액·단열 효과 숫자 지어내지 않음)**
* 필요한 라디에이터 정격 증가량: `ΣΦ_n,needed(55°C) − ΣΦ_n` → "라디에이터 출력 약 X kW 추가"
* 또는 필요한 부하 감소율: `1 − P_load,allowed(55°C) / P_load` → "열손실이 약 Y% 줄면 노랑/초록" (어떤 단열이 몇 % 줄이는지는 말하지 않음, 기사·에너지 컨설팅으로)

**7. 불확실성**
비어 있는 인자를 사전분포에서 샘플링해 N=500 몬테카를로. 출력은 전부 p10~p90 범위 + 신호등 확률.
최대 확률 < 0.6 이면 `unclear` + 다음 사진 미션.

**8. 다음 질문**
비어 있는 인자 각각에 대해: 그 인자를 고정했을 때 신호등 분포 엔트로피가 얼마나 줄어드는지 계산 → 가장 많이 줄이는 1개.

**9. 기사 브리핑**
* 항상: 실외기 위치·소음 거리, 전기 인입 용량, 수력 밸런싱
* 불확실했던 인자: "거실 라디에이터 출력 부족 의심", "단관식 가능성 높음 → 배관 확인" 등
* 신호등 이유와 예상 범위 요약

## 입력 설계 (`schema.py`)

원칙: 형식 안 가리기 / 사진 한 장으로 필드 여러 개 / 정보가치 낮은 건 묻지 말고 사전분포로.
각 필드에 `effort` 점수(1~3). 다음 질문 = 엔트로피 감소량 ÷ effort 최대.

**드롭다운 (사진 없이 30초)**: 건물 유형, 대략 년식, 면적, 거주 인원, 연료, 바닥난방 여부, 라디에이터 개수, 창문 교체 여부, 문화재 여부, 월 선납금(Abschlag, 선택)
라디에이터 크기 드롭다운은 작음/중간/큼 **그림 선택**으로.

**핵심 사진 3장** (드롭다운 값이 있으면 사진이 덮어씀, confidence 높은 쪽 우선)

1. 외관 — "Ganzes Haus von der Straße fotografieren, mit Dach und etwas Umgebung"
   → `building_type`, `build_year`(범위), `windows`, 외단열 흔적, 지붕 상태, 실외기 자리 힌트, 문화재 느낌
2. 고지서 — "Heizkostenabrechnung in beliebiger Form: Foto, PDF oder Screenshot aus der App"
   → `fuel_type`, `annual_fuel_kwh`(m³·상태수·발열량 섞여 있어도 kWh 골라서 365일 환산), 청구기간
3. 거실 라디에이터 — "Größter Heizkörper im Wohnzimmer, schräg von der Seite, mit den Rohren darunter"
   → `radiator_type`(비스듬히 찍어야 판 개수 보임), 크기(콘센트·창틀 기준, A4는 선택), `pipe_system`, 밸브·온도조절기

**선택 사진 (엔진이 요청할 때만)**

4. 바닥난방 분배기 → `heat_distribution` 확정, 회로 수
5. 보일러 앞면 전체 (명판 말고) → `boiler_condensing`(플라스틱 배기관·응축수 배수관), 연식, 디스플레이 공급온도
6. 실외기 후보 위치 → `outdoor_unit_space` (소음 거리 확정은 기사 체크리스트)

**재촬영 루프**

* 각 사진 미션에 **예시 이미지**(어디를 어떻게 찍는지) 표시
* 추출 시 필드마다 null이면 `missing_reason` 반환: `not_visible` | `blurry` | `ambiguous` | `wrong_object`
  → LLM은 이유 코드만 냄 (판정 아님). 문구는 app.py가 매핑: 예) `pipe_system`+`not_visible` → "Die Rohre unter dem Heizkörper sind nicht im Bild. Bitte etwas tiefer fotografieren."
* **부분 수용**: 크기는 나오고 배관만 안 보이면 크기는 저장, 배관만 다시 요청
* **재시도 최대 2회** → 그래도 null이면 드롭다운/사전분포로 대체하고 기사 체크리스트에 추가. 무한루프 금지
* 데모: 일부러 배관 안 나온 사진 먼저 → 구체적 재촬영 안내 → 좋은 사진 → 범위 좁아짐 (캐시로 준비)

## 화면 (`app.py`)

* 🏠 Homeowner: 업로드 + `st.camera_input` → 추출 결과(신뢰도) → 신호등 + 이유 → 비용 범위 → 다음 사진 미션 1개. 사진 추가할 때마다 범위가 좁아지는 게 보이게
* 🔧 Installer: 기사 브리핑, 채워진 스키마, 빈 칸, 필요 공급온도·부하 범위, 방문 분류(짧은 방문 / 브리핑 들고 방문 / 방문 안 함 + 리드 보관)
* 📊 Evaluation: 5채 로드 → 3채는 기준값과 나란히 비교, 2채는 결과만. **피치에서 이 화면 사용**
* 사이드바 Demo mode 토글: 켜면 LLM 대신 `samples/cached_extract.json`

## 작업 방식 (에이전트 운용)

* **레인 최대 2개.** 레인 A = schema·loader·engine·calibrate, 레인 B = app.py(+extract). B는 `evaluate()`가 없으면 `Result` 더미를 반환하는 스텁으로 먼저 UI를 만든다. 인터페이스 계약만 지키면 충돌 없음
* 같은 파일을 두 세션이 동시에 고치지 않는다
* **`/check` 통과할 때마다 커밋.** 터지면 `git restore`/마지막 커밋으로 즉시 롤백. 커밋 없이 30분 넘게 작업 금지
* P0-a 끝, P0-b 끝, 코드 동결 직전에 **`/review`** (작업 안 본 별도 에이전트 검수)
* 현장 정보는 전부 **`/intake`** 로 받는다
* 슬래시 커맨드: `.claude/commands/` 의 `intake`, `check`, `review`

## 코딩 규칙

* 기존 함수 시그니처 유지. 필요하면 새 함수 추가.
* LLM 호출·파일 입력은 전부 try/except. 실패 시 캐시로 대체하고 화면에 작게 표시.
* 고지서는 PDF도 받음(API 문서 입력). 원본·이름·주소는 저장하지 않고 추출한 숫자만 세션에 유지.
* UI에 Key terms 4개(Heizlast, Vorlauftemperatur, JAZ, Ein-/Zweirohr)가 결과와 함께 보이게, ⓘ 툴팁으로 설명.
* 한 번에 한 기능만 수정. 수정 후 `streamlit run app.py`로 해피패스 확인.
* 설명은 짧게. 바로 코드.

## 데모 해피패스

(페르소나: 1972년 연립주택 140m², 3인, 가스)
드롭다운 7개 → ❔ unclear, 확률 분산 → "고지서 아무 형식으로" →
앱 스크린샷 → 연간 kWh 추출, 비용 표시, 여전히 초록/노랑 갈림 → "거실 라디에이터 비스듬히 + 배관" →
배관 잘린 사진 → 크기만 저장, "조금 더 아래로" 재촬영 안내 →
재촬영 → 🟡 + 공급온도 밴드 좁아짐 + 비용 두 시나리오(그대로 / 라디에이터 교체) + 기사 확인 항목 →
🔧 Installer 탭 브리핑 → 📊 Evaluation 탭 2채 결과
(전부 캐시로 리허설. P1이 잘리면 확률·재촬영 없이 같은 순서로)

## "돌아간다" 증명 장면 (데모에 반드시 포함)

1. **정확도**: Evaluation 탭 — 3채 오차, leave-one-out, 평가 2채 결과
2. **지어내지 않음**: 엉뚱한 사진(고양이 등) → `wrong_object`, 값 null, 판정 안 바뀜
3. **모르면 모른다고 함**: 정보 부족 → ❔ unclear + 사진 하나만 요청
4. **재촬영 루프**: 배관 잘린 사진 → 구체적 안내 → 재촬영 → 밴드 좁아짐
5. **근거 추적**: Rechenweg 펼쳐서 숫자 체인 보여주기
6. **결정론**: 같은 입력 두 번 → 같은 결과
7. **라이브 한 방(선택)**: 발표장 라디에이터를 폰으로 즉석 촬영. 실패하면 Demo mode 캐시로 즉시 전환
* 백업: 해피패스 화면 녹화 영상 준비 (와이파이 사망 대비, 발표는 라이브 우선)

## 피치 핵심 문장

* "In Germany, the scarcest resource isn't energy. It's the installer's time."
* "The LLM reads. Physics decides. Nothing is made up."
* "We only ask for the one photo that actually changes the answer."
* "We don't cancel site visits. We make them short and precise."
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
  * 난방부하(kW) 있음 → t_vbh 또는 도일법 선택으로 보정
  * 공급온도 있음 → 라디에이터 룩업 스케일 / 단관 패널티 보정
  * 신호등만 있음 → 색 경계(55/60, 부족분 25%)만 맞춤
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

- [ ] 기준값 형식 (난방부하 / 공급온도 / 신호등 / 비용 중 무엇)
- [ ] CSV/JSON 필드명
- [ ] 건물 위치 → 설계 외기온도·도일
- [ ] 평가 2채에 사진 포함 여부
- [ ] 팀 규모·역할
- [ ] 사전 코드 작성 허용 여부

### 결정 로그 (형식: `HH:MM 무엇을 왜 바꿈`)

- (시작 전) kNN+가짜 DB → 물리 엔진. 이유: 심사가 실제 2채 기준값 대비 정확도, synthetic DB는 방어 불가

---

## 도메인 배경 (사람·에이전트 공용 입문서)

**히트펌프**: 열을 만드는 게 아니라 바깥 공기에서 옮겨옴. 전기 1 kWh → 열 3~4 kWh. 이 연간 평균 비율이 **JAZ**.

**왜 공급온도(Vorlauftemperatur)가 전부인가**: 히트펌프는 물을 덜 뜨겁게 데울수록 효율이 높음. 바깥 공기와 목표 물 온도 차이가 클수록 압축기가 더 일해야 해서. 그래서 "우리 집 되냐" = "미지근한 물로도 집이 따뜻하냐".

**55 / 60°C의 의미**: 챌린지 JAZ 표의 구간 경계. ≤55 → JAZ 3.5, 55~60 → 2.8, 표가 60에서 끝남 → 그 위는 이 챌린지 가정으로는 권장 불가. 우리가 정한 숫자가 아님.

**필요 공급온도의 정의**: 그 지역 설계 외기온도(가장 추운 날 기준값)에서 기존 라디에이터로 실내 20°C를 유지하는 데 필요한 물 온도. 한겨울 최악 조건 기준이라는 게 핵심.

**난방부하(Heizlast)**: 그 최악의 날에 집이 잃는 열(kW). 우리는 측정 못 하니까 연간 연료 소비량에서 역산. 이게 "추정"의 정체.

**추정 체인과 가정** (각 화살표마다 가정이 하나씩 끼어 있음 = 불확실성의 출처)
`고지서 kWh` →(보일러 효율 η)→ `실제 열` →(온수분 차감)→ `난방열` →(풀부하시간 또는 도일)→ `난방부하 kW` →(라디에이터 총출력)→ `필요 공급온도` →(JAZ 표)→ `비용·신호등`
가장 큰 불확실성: 라디에이터 총출력 > 난방부하 방법 > 온수 > 효율.

**라디에이터 출력식**: 라디에이터는 물이 식으면 열을 덜 냄. 정격(75°C 물 기준)의 출력이 55°C 물에선 약 절반. 옛날 집은 원래 90°C 기준으로 라디에이터를 크게 달아놔서, 낮은 온도에서도 버티는 경우가 많음 → "생각보다 많은 집이 된다".

**단관식 / 복관식 (Ein-/Zweirohrheizung)**: 복관은 각 라디에이터에 뜨거운 물이 따로 들어감. 단관은 한 줄 파이프에 라디에이터가 줄줄이 달려서, 뒤쪽일수록 식은 물을 받음 → 공급온도를 더 높여야 함 → 히트펌프에 불리. 60~70년대 건물에 흔함.

**몬테카를로**: 모르는 값(예: 라디에이터 총출력)에 숫자 하나를 찍지 않고, 그럴듯한 범위에서 500번 랜덤으로 뽑아 엔진을 500번 돌림. 결과 분포 → 범위(p10~p90)와 색 확률. 엔진은 그대로, 반복문으로 감쌀 뿐. "다음 질문"은 각 미지 값을 안다고 치고 다시 돌렸을 때 결과가 가장 선명해지는 걸 고름.

**보정(calibration)**: 3채 = 학습셋, 2채 = 테스트셋. 3채에서 엔진 값과 nuuEnergy 기준값을 비교해 상수 1~2개만 조정. 점 3개로 많이 맞추면 과적합 → 2채에서 터짐.

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
