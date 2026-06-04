# 메이플스토리 자동사냥 매크로 — Claude Code 프로젝트 가이드

## 프로젝트 개요

메이플 플래닛 PC 클라이언트용 자동화 매크로.
화면 인식(OpenCV + YOLOv8) 기반, 메모리 직접 읽기 없음.
대상 맵: 빨간 코끼리 2 / 빨간 코끼리 2 미니던전

### 라이선스 등급

| 등급 | 설명 |
|------|------|
| FREE | 라이선스 키 없음, 기본 기능만 사용 가능 |
| BASIC | 라이선스 키 필요, 기본 기능 |
| PREMIUM | 라이선스 키 필요, 전체 기능 |

### 등급별 기능 제한

| 기능 | FREE | BASIC | PREMIUM |
|------|------|-------|---------|
| 패턴 방식 자동사냥 | 가능 | 가능 | 가능 |
| HP/MP 포션 자동 사용 | 가능 | 가능 | 가능 |
| 텔레그램 알림 | 가능 | 가능 | 가능 |
| 상태 감시 (정지/반복 감지) | 가능 | 가능 | 가능 |
| 모드 선택 | 저스펙만 | 저스펙만 | 고스펙+저스펙 |
| 맵 선택 | 1개 고정 | 전체 | 전체 |
| YOLO 방식 자동사냥 | 불가 | 불가 | 가능 |
| 매매 루틴 | 불가 | 불가 | 가능 |
| 거탐 감지 | 불가 | 불가 | 가능 |

---

## 기술 스택

- **언어**: Python 3.10+
- **화면 캡처**: mss
- **화면 인식**: opencv-python, numpy
- **객체 탐지**: ultralytics (YOLOv8) — PREMIUM 전용
- **입력 제어**: pyautogui, pynput
- **핫키**: keyboard
- **알림**: python-telegram-bot
- **설정 UI**: tkinter (내장)
- **설정 저장**: json
- **라이선스**: 하이브리드 방식 (최초 온라인 인증 → 이후 로컬 하드웨어 ID 검증)

```bash
pip install opencv-python mss pyautogui pynput keyboard python-telegram-bot numpy Pillow ultralytics requests
```

---

## 프로젝트 구조

```
game_macro/
├── CLAUDE.md                   ← 이 파일
├── main.py                     ← 진입점, 핫키 토글, 메인 루프
├── config.py                   ← 상수/기본값 (딜레이, 키 바인딩)
├── config.json                 ← 사용자 설정 저장 (런타임 생성)
│
├── license/
│   ├── license_manager.py      ← 라이선스 검증 총괄
│   ├── hardware_id.py          ← 하드웨어 ID 생성 (CPU+MAC 조합)
│   ├── local_validator.py      ← 로컬 암호화 키 검증
│   └── online_validator.py     ← 온라인 서버 검증 (최초 1회)
│
├── screen_capture.py           ← 화면 캡처 + OpenCV 분석
├── input_controller.py         ← 키보드/마우스 입력 + 랜덤 딜레이
├── monitor.py                  ← 상태 감시 (정지/반복/마을/감옥/거탐)
├── telegram_bot.py             ← 텔레그램 알림 전송
├── shop_routine.py             ← 매매 루틴 [PREMIUM]
├── settings_ui.py              ← tkinter 설정 창
│
├── hunting/
│   ├── base_hunter.py          ← 사냥 루틴 공통 인터페이스 (추상 클래스)
│   ├── pattern_hunter.py       ← 패턴 방식 사냥 [FREE/BASIC/PREMIUM]
│   └── yolo_hunter.py          ← YOLO 방식 사냥 [PREMIUM]
│
└── assets/
    ├── hp_bar.png
    ├── mp_bar.png
    ├── buff_icons/
    ├── minimap/
    │   └── char_dot.png
    ├── map_markers/
    ├── shop/
    ├── gm_detect/              ← 거탐 템플릿 [PREMIUM]
    └── yolo_models/
        └── maple_monster.pt    ← 학습된 YOLOv8 모델 [PREMIUM]
```

---

## 코드 규칙 (반드시 준수)

1. **모든 함수에 한국어 docstring 작성**
2. **모든 딜레이는 `random.uniform(min, max)` 사용** — 고정값 절대 금지
3. **설정값은 config.py 또는 config.json에서만 관리** — 하드코딩 금지
4. **화면 인식은 OpenCV + YOLOv8만 사용** — 다른 딥러닝 프레임워크 혼용 금지
5. **메모리 직접 읽기 사용 금지**
6. **예외처리 필수** — try/except 없는 함수 작성 금지
7. **로그는 print 대신 logging 모듈 사용**
8. **PREMIUM 전용 기능은 반드시 라이선스 체크 후 실행**

```python
# PREMIUM 기능 호출 예시
from license.license_manager import require_tier

@require_tier('PREMIUM')  # 데코레이터로 간단하게 처리
def run_yolo_hunter():
    ...
```

### 딜레이 규칙

```python
import random, time

# 금지
time.sleep(0.5)

# 권장
time.sleep(random.uniform(0.4, 0.7))
```

---

## 라이선스 시스템 설계

### 동작 방식 (하이브리드)

```
최초 실행
    ↓
라이선스 키 입력
    ↓
[온라인] 서버에 키 + 하드웨어ID 전송
    ↓
서버가 등급 확인 후 서명된 토큰 발급
    ↓
[로컬] 암호화된 토큰을 license.dat에 저장
    ↓
이후 실행부터는 license.dat + 하드웨어ID만으로 검증
(인터넷 불필요)
```

### hardware_id.py 핵심 패턴

```python
import hashlib, uuid, subprocess

def get_hardware_id() -> str:
    """CPU ID + MAC 주소를 조합해 고유한 하드웨어 ID 생성"""
    try:
        mac = hex(uuid.getnode())
        cpu = subprocess.check_output('wmic cpu get ProcessorId',
                                      shell=True).decode().strip().split()[-1]
        raw = f"{mac}-{cpu}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    except Exception as e:
        logging.error(f"하드웨어 ID 생성 실패: {e}")
        return hashlib.sha256(mac.encode()).hexdigest()[:32]
```

### license_manager.py 핵심 패턴

```python
from functools import wraps

TIER_LEVELS = {'FREE': 0, 'BASIC': 1, 'PREMIUM': 2}

class LicenseManager:
    def get_tier(self) -> str:
        """현재 라이선스 등급 반환 — FREE / BASIC / PREMIUM"""
        ...

    def is_allowed(self, required_tier: str) -> bool:
        """현재 등급이 required_tier 이상인지 확인"""
        current = TIER_LEVELS.get(self.get_tier(), 0)
        required = TIER_LEVELS.get(required_tier, 999)
        return current >= required

def require_tier(tier: str):
    """라이선스 등급 체크 데코레이터"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not license_manager.is_allowed(tier):
                raise PermissionError(
                    f"이 기능은 {tier} 등급 이상에서만 사용 가능합니다."
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator

license_manager = LicenseManager()
```

---

## 사냥 방식 구조 설계

### base_hunter.py — 공통 인터페이스

```python
from abc import ABC, abstractmethod

class BaseHunter(ABC):
    """모든 사냥 방식이 상속받는 추상 클래스"""

    @abstractmethod
    def find_monsters(self) -> list:
        """현재 화면에서 몬스터 위치 목록 반환"""
        pass

    @abstractmethod
    def decide_action(self, monsters: list) -> str:
        """몬스터 상태를 보고 다음 행동 결정"""
        pass

    def run_loop(self):
        """공통 사냥 루프 — 두 방식 모두 동일하게 사용"""
        while True:
            monsters = self.find_monsters()
            action = self.decide_action(monsters)
            self.execute_action(action)
```

### pattern_hunter.py — 패턴 방식 [FREE/BASIC/PREMIUM]

```python
class PatternHunter(BaseHunter):
    """타이머 기반 패턴 이동 사냥"""

    def find_monsters(self) -> list:
        # 몬스터 위치 탐지 없음 — 항상 빈 리스트 반환
        return []

    def decide_action(self, monsters: list) -> str:
        # 시간 기반으로 이동/스킬 결정
        return self._get_next_pattern_action()
```

### yolo_hunter.py — YOLO 방식 [PREMIUM]

```python
from license.license_manager import require_tier
from ultralytics import YOLO

class YoloHunter(BaseHunter):
    """YOLOv8 기반 몬스터 감지 사냥"""

    @require_tier('PREMIUM')
    def __init__(self):
        self.model = YOLO('assets/yolo_models/maple_monster.pt')

    def find_monsters(self) -> list:
        """화면에서 몬스터 위치 목록 반환 (바운딩박스 좌표)"""
        screen = capture_full_screen()
        results = self.model(screen)
        return results[0].boxes.xyxy.tolist()

    def decide_action(self, monsters: list) -> str:
        if not monsters:
            return 'move'          # 몬스터 없으면 이동
        return 'attack'            # 몬스터 있으면 공격
```

### main.py — 방식 선택 분기

```python
from license.license_manager import license_manager
from hunting.pattern_hunter import PatternHunter
from hunting.yolo_hunter import YoloHunter

def create_hunter():
    """설정 + 라이선스에 따라 사냥 방식 결정"""
    mode = config_json.get('hunt_mode', 'pattern')
    if mode == 'yolo' and license_manager.is_allowed('PREMIUM'):
        return YoloHunter()
    return PatternHunter()  # 기본값 또는 권한 없을 때
```

---

## 개발 단계 (순서대로 구현)

### PHASE 1 — 뼈대
> 목표: 프로그램이 켜지고 꺼지는 것 확인

- [ ] `config.py` — 키 바인딩, 딜레이 상수 정의
- [ ] `main.py` — F9 시작/중지, F10 종료 핫키 등록
- [ ] `input_controller.py` — 랜덤 딜레이 키 입력 함수
- [ ] `screen_capture.py` — mss 전체화면 캡처 확인
- [ ] 실행 테스트 — F9/F10 핫키 동작 확인

**완료 기준**: F9/F10 핫키 정상 동작, 화면 캡처 이미지 저장됨

---

### PHASE 2 — 라이선스 시스템
> 목표: 실행 시 라이선스 검증 후 등급에 따라 기능 제한

- [ ] `license/hardware_id.py` — 하드웨어 ID 생성
- [ ] `license/local_validator.py` — 로컬 license.dat 파일 검증
- [ ] `license/online_validator.py` — 온라인 서버 검증 (stub으로 먼저 구현)
- [ ] `license/license_manager.py` — 등급 확인 + `@require_tier` 데코레이터
- [ ] `main.py` — 시작 시 라이선스 검증 연결
- [ ] 실행 테스트 — FREE/BASIC/PREMIUM 각 등급으로 기능 제한 확인

**완료 기준**: 등급별로 허용/차단 기능이 정확히 분리됨

**참고**: 온라인 서버는 나중에 실제로 연결. 지금은 stub 함수로 항상 PREMIUM 반환해서 개발 진행

---

### PHASE 3 — HP/MP 포션 자동 사용
> 목표: HP/MP가 일정 % 이하면 자동으로 포션 키 입력

- [ ] `screen_capture.py` — HSV 색상 범위로 HP/MP바 비율 계산
- [ ] `config.py` — HP/MP 임계값(%), 포션 키 설정
- [ ] `macro_logic.py` — `check_and_use_potion()` 함수
- [ ] 실행 테스트 — HP바 줄이면서 포션키 자동 입력 확인

**완료 기준**: HP 50% 이하 시 자동으로 포션 키가 눌림

```python
# HP바 색상 (HSV) — 실제 게임에서 캡처 후 보정 필요
HP_COLOR_LOWER = np.array([0, 100, 100])
HP_COLOR_UPPER = np.array([10, 255, 255])
```

---

### PHASE 4 — 스킬 콤보 자동화
> 목표: 설정한 순서대로 스킬 키를 자동 입력

- [ ] `config.py` — 모드1(고스펙)/모드2(저스펙) 스킬 콤보 설정
- [ ] `macro_logic.py` — `execute_skill_combo()` 함수
- [ ] 라이선스 체크 — 고스펙 모드는 PREMIUM만 가능
- [ ] 실행 테스트 — 더미 창에서 스킬 키 순서 확인

**완료 기준**: 등급에 맞는 스킬 콤보가 랜덤 딜레이로 입력됨

---

### PHASE 5 — 미니맵 좌표 인식
> 목표: 미니맵에서 캐릭터 위치(X, Y)를 실시간으로 읽기

- [ ] `assets/minimap/char_dot.png` 템플릿 이미지 준비
- [ ] `screen_capture.py` — `get_character_position()` 함수
- [ ] `config.py` — 미니맵 화면 좌표(x, y, w, h) 설정
- [ ] 실행 테스트 — 이동할 때마다 좌표 출력 확인

**완료 기준**: 캐릭터 이동 시 미니맵 좌표가 실시간으로 변경됨

---

### PHASE 6 — 패턴 방식 자동 이동 [FREE/BASIC/PREMIUM]
> 목표: 1층/2층을 왔다갔다하며 좌우 이동 패턴 실행

- [ ] `hunting/base_hunter.py` — 추상 클래스 정의
- [ ] `hunting/pattern_hunter.py` — 타이머 기반 패턴 이동 구현
  - `move_left_right()` 좌우 이동
  - `move_to_floor(floor)` 층 이동
  - `floor_recovery()` 실패 재시도
  - `run_loop()` 전체 사냥 루프
- [ ] `main.py` — `PatternHunter` 연결
- [ ] 실행 테스트 — 빨코2 맵에서 실제 이동 패턴 확인

**완료 기준**: 캐릭터가 1층-2층을 자동으로 오가며 스킬을 사용함

---

### PHASE 7 — 상태 감시 시스템
> 목표: 비정상 상황 감지 시 자동 정지

- [ ] `monitor.py` — `detect_position_stuck()` 장시간 정지 감지
- [ ] `monitor.py` — `detect_position_loop()` 같은 좌표 반복 감지
- [ ] `monitor.py` — `detect_town()` 마을 이동 감지
- [ ] `monitor.py` — `detect_jail()` 감옥 감지
- [ ] `main.py` — 감지 시 매크로 자동 정지 연결
- [ ] 실행 테스트 — 캐릭터를 마을로 이동시켜 감지 확인

**완료 기준**: 마을/감옥 진입 또는 캐릭터 정지 시 매크로 자동 중단

---

### PHASE 8 — 텔레그램 알림
> 목표: 이상 상황 발생 시 텔레그램으로 알림 + 스크린샷 전송

- [ ] 텔레그램 봇 생성 (BotFather에서 토큰 발급)
- [ ] `telegram_bot.py` — `send_message()`, `send_screenshot()` 함수
- [ ] `config.json` — TELEGRAM_TOKEN, CHAT_ID 저장
- [ ] `main.py` — 시작/정지/이상상황에 알림 연결
- [ ] 실행 테스트 — F9 누르면 텔레그램 알림 수신 확인

**완료 기준**: 시작/정지/이상상황 시 텔레그램 알림 수신

```python
# 텔레그램 설정 방법
# 1. 텔레그램에서 @BotFather 검색
# 2. /newbot 명령으로 봇 생성 → 토큰 발급
# 3. 봇에게 아무 메시지 전송 후 아래 URL로 chat_id 확인
#    https://api.telegram.org/bot{토큰}/getUpdates
```

---

### PHASE 9 — 매매 루틴 [PREMIUM]
> 목표: 주기마다 상점 이동 → 판매 → 소모품 구매 → 복귀

- [ ] `shop_routine.py` — `go_to_shop()`, `sell_items()`, `buy_consumables()`, `return_to_hunting()`
- [ ] `config.json` — 상점 주기, 소모품 구매 수량 설정
- [ ] `main.py` — 타이머로 매매 루틴 주기 실행 연결
- [ ] `@require_tier('PREMIUM')` 데코레이터 적용
- [ ] 실행 테스트 — 수동으로 매매 루틴 트리거해서 전체 흐름 확인

**완료 기준**: 설정 주기마다 상점 이동 → 판매 → 구매 → 복귀 자동 실행

---

### PHASE 10 — 설정 UI (tkinter)
> 목표: GUI로 설정값을 저장/불러오기

- [ ] `settings_ui.py` — tkinter 설정 창 구현
  - 라이선스 키 입력 및 등급 표시
  - 사냥 방식 선택 (패턴 / YOLO) — PREMIUM만 YOLO 선택 가능
  - 맵 선택 (빨코2 / 빨코2 미니던전) — PREMIUM만 전체 선택 가능
  - 모드 선택 (고스펙 / 저스펙) — PREMIUM만 고스펙 선택 가능
  - 소모품 구매 수량, 상점 주기, 펫먹이 주기, 텔레포트 주기
  - 텔레그램 토큰 / 채팅ID 입력
- [ ] `config.json` 읽기/쓰기 연결
- [ ] 실행 테스트 — 설정 저장 후 재실행해도 값 유지 확인

**완료 기준**: GUI로 설정 변경 → config.json 저장 → 재실행 시 불러와짐

---

### PHASE 11 — YOLO 방식 자동사냥 [PREMIUM]
> 목표: YOLOv8으로 몬스터 실시간 감지 후 지능형 사냥

**선행 작업 — 학습 데이터 준비**
- [ ] 빨코2 몬스터 스크린샷 최소 200장 수집
- [ ] Roboflow 또는 LabelImg로 바운딩박스 라벨링
- [ ] YOLOv8 모델 학습 (`yolo train ...`)
- [ ] `assets/yolo_models/maple_monster.pt` 저장

**구현**
- [ ] `hunting/yolo_hunter.py` — `YoloHunter` 클래스 구현
  - `find_monsters()` — YOLOv8으로 몬스터 위치 탐지
  - `decide_action()` — 몬스터 있으면 공격, 없으면 이동
  - 몬스터 죽을 때까지 스킬 사용 로직
- [ ] `@require_tier('PREMIUM')` 데코레이터 적용
- [ ] `main.py` — 설정에 따라 `YoloHunter` 또는 `PatternHunter` 선택
- [ ] 실행 테스트 — 몬스터 감지 박스 시각화로 정확도 확인

**완료 기준**: 몬스터 있을 때만 공격, 없으면 다음 위치로 이동

```python
# YOLO 학습 명령어 (터미널)
# yolo task=detect mode=train model=yolov8n.pt data=maple.yaml epochs=100 imgsz=640
```

---

### PHASE 12 — 거탐(GM) 감지 [PREMIUM, 마지막]
> 목표: 거대한 탐정 등장 시 즉시 감지 + 알림 + 매크로 정지

- [ ] 거탐 등장 UI 화면 캡처 (여러 상황에서 수집)
- [ ] `assets/gm_detect/` 폴더에 템플릿 이미지 저장
- [ ] `monitor.py` — `detect_gm()` 다중 템플릿 매칭 함수
- [ ] 매크로 즉시 정지 + 텔레그램 스크린샷 알림 연결
- [ ] `@require_tier('PREMIUM')` 데코레이터 적용
- [ ] 실행 테스트 — 임계값 튜닝 (권장: 0.75 ~ 0.85)

**완료 기준**: 거탐 UI 등장 시 1초 이내 감지 + 매크로 정지 + 텔레그램 알림

---

## config.py 기본 구조

```python
# 핫키
HOTKEY_TOGGLE = 'f9'
HOTKEY_EXIT   = 'f10'

# 딜레이 범위 (초)
DELAY_KEY_MIN  = 0.05
DELAY_KEY_MAX  = 0.15
DELAY_LOOP_MIN = 0.08
DELAY_LOOP_MAX = 0.20

# 포션 설정
HP_POTION_KEY      = '1'
MP_POTION_KEY      = '2'
HP_THRESHOLD_PCT   = 50    # HP 50% 이하시 포션
MP_THRESHOLD_PCT   = 30    # MP 30% 이하시 포션
HP_POTION_COOLDOWN = 1.5   # 포션 쿨타임(초)

# 화면 설정 (1920x1080 기준)
MINIMAP_REGION = {'x': 1720, 'y': 10,  'w': 180, 'h': 120}
HP_BAR_REGION  = {'x': 100,  'y': 50,  'w': 200, 'h': 20}
MP_BAR_REGION  = {'x': 100,  'y': 75,  'w': 200, 'h': 20}

# 층 이동 기준 (미니맵 Y좌표)
FLOOR2_Y_THRESHOLD = 40

# 스킬 콤보 [(키, 딜레이(초)), ...]
SKILL_COMBO_MODE1 = [('z', 0.3), ('x', 0.3), ('c', 0.8), ('v', 0.3)]
SKILL_COMBO_MODE2 = [('z', 0.5), ('x', 0.5)]

# 상점 주기 (초)
SHOP_INTERVAL = 1800   # 30분

# OpenCV 매칭 임계값
TEMPLATE_MATCH_THRESHOLD = 0.80

# YOLO 설정
YOLO_MODEL_PATH       = 'assets/yolo_models/maple_monster.pt'
YOLO_CONFIDENCE       = 0.5
YOLO_CAPTURE_REGION   = {'x': 0, 'y': 0, 'w': 1920, 'h': 1080}
```

---

## 자주 쓰는 Claude Code 명령어 패턴

```
# 단계 시작
"CLAUDE.md의 PHASE 2 라이선스 시스템을 구현해줘.
 online_validator는 지금은 항상 PREMIUM을 반환하는 stub으로 만들고,
 @require_tier 데코레이터 테스트 코드도 함께 작성해줘"

# 기능 추가
"hunting/yolo_hunter.py를 CLAUDE.md의 설계대로 구현해줘.
 find_monsters()는 YOLOv8 결과를 바운딩박스 리스트로 반환하고,
 모델 파일 없을 때 FileNotFoundError 대신 친절한 안내 메시지 출력해줘"

# 디버깅
"screen_capture.py의 find_template 함수가 항상 None을 반환해.
 매칭 점수를 로그로 출력하는 디버그 모드 추가하고
 임계값을 파라미터로 받을 수 있게 수정해줘"

# 테스트 스크립트
"test_phase3.py를 만들어줘.
 HP/MP 색상 인식이 잘 되는지 확인하는 스크립트.
 현재 HP%, MP%를 1초마다 콘솔에 출력하고 q키로 종료되게"
```

---

## 주의사항 / 트러블슈팅

### 화면 좌표
- 모든 좌표는 **1920x1080 기준** — 다른 해상도면 config.py REGION 직접 수정
- 게임 창이 전체화면이 아니면 좌표 달라짐 — 전체화면 모드 권장

### OpenCV 템플릿 매칭 오류
- 템플릿 이미지는 **실제 게임에서 직접 캡처** (인터넷 이미지 X)
- 매칭 안 될 때: threshold를 0.70까지 낮추고 max_val 로그 확인

### YOLO 관련
- `maple_monster.pt` 없으면 YOLO 방식 실행 불가 → 패턴 방식으로 자동 폴백
- GPU 없으면 CPU로 실행 (느리지만 동작함)
- 학습 데이터 라벨링 도구: https://roboflow.com (무료)

### pyautogui
- `pyautogui.FAILSAFE = True` 유지 필수
- 관리자 권한으로 실행해야 키 입력이 게임에 전달됨

### 라이선스 서버
- PHASE 2에서는 stub으로 개발, 나중에 실제 서버 연결
- 서버 옵션: Oracle Cloud 무료티어 (항상 무료) 추천

---

## 현재 구현 상태

- [ ] PHASE 1  — 뼈대
- [ ] PHASE 2  — 라이선스 시스템
- [ ] PHASE 3  — HP/MP 포션
- [ ] PHASE 4  — 스킬 콤보
- [ ] PHASE 5  — 미니맵 좌표
- [ ] PHASE 6  — 패턴 방식 자동이동
- [ ] PHASE 7  — 상태 감시
- [ ] PHASE 8  — 텔레그램 알림
- [ ] PHASE 9  — 매매 루틴 [PREMIUM]
- [ ] PHASE 10 — 설정 UI
- [ ] PHASE 11 — YOLO 방식 사냥 [PREMIUM]
- [ ] PHASE 12 — 거탐 감지 [PREMIUM]