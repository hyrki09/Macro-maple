"""게임 매크로 전역 설정 상수 모듈.

모든 키 바인딩, 딜레이 범위, 화면 좌표(REGION), 임계값을 한곳에서 관리한다.
런타임에 바뀌는 사용자 설정은 config.json 에서 따로 로드하며,
이 파일에는 변하지 않는 기본 상수만 둔다. (코드 규칙 3: 하드코딩 금지)
"""

import numpy as np

# ===== 핫키 =====
HOTKEY_TOGGLE = 'f9'    # 매크로 시작/중지 토글
HOTKEY_EXIT   = 'f10'   # 프로그램 완전 종료

# ===== 딜레이 범위 (초) =====
# 코드 규칙 2: 모든 딜레이는 random.uniform(min, max) 로 사용한다. 고정값 금지.
DELAY_KEY_MIN  = 0.05   # 키 입력 사이 최소 딜레이
DELAY_KEY_MAX  = 0.15   # 키 입력 사이 최대 딜레이
DELAY_LOOP_MIN = 0.08   # 메인 루프 1회전 최소 딜레이
DELAY_LOOP_MAX = 0.20   # 메인 루프 1회전 최대 딜레이

# ===== 포션 설정 =====
HP_POTION_KEY      = '1'
MP_POTION_KEY      = '2'
HP_THRESHOLD_PCT   = 50     # HP 50% 이하 시 포션
MP_THRESHOLD_PCT   = 30     # MP 30% 이하 시 포션
HP_POTION_COOLDOWN = 1.5    # 포션 쿨타임(초)

# ===== 화면 설정 (1920x1080 기준) =====
# 다른 해상도면 아래 REGION 값을 직접 보정해야 한다.
MINIMAP_REGION = {'x': 1720, 'y': 10, 'w': 180, 'h': 120}
HP_BAR_REGION  = {'x': 100,  'y': 50, 'w': 200, 'h': 20}
MP_BAR_REGION  = {'x': 100,  'y': 75, 'w': 200, 'h': 20}

# 전체 화면 캡처 영역 (디버그/YOLO 공용)
FULL_SCREEN_REGION = {'x': 0, 'y': 0, 'w': 1920, 'h': 1080}

# ===== 층 이동 기준 (미니맵 Y좌표) =====
FLOOR2_Y_THRESHOLD = 40

# ===== HP/MP 바 색상 (HSV) — 실제 게임 캡처 후 보정 필요 =====
HP_COLOR_LOWER = np.array([0, 100, 100])
HP_COLOR_UPPER = np.array([10, 255, 255])

# ===== 스킬 콤보 [(키, 딜레이(초)), ...] =====
SKILL_COMBO_MODE1 = [('z', 0.3), ('x', 0.3), ('c', 0.8), ('v', 0.3)]   # 고스펙 [PREMIUM]
SKILL_COMBO_MODE2 = [('z', 0.5), ('x', 0.5)]                            # 저스펙

# ===== 상점 주기 (초) =====
SHOP_INTERVAL = 1800   # 30분

# ===== OpenCV 매칭 임계값 =====
TEMPLATE_MATCH_THRESHOLD = 0.80

# ===== YOLO 설정 =====
YOLO_MODEL_PATH     = 'assets/yolo_models/maple_monster.pt'
YOLO_CONFIDENCE     = 0.5
YOLO_CAPTURE_REGION = {'x': 0, 'y': 0, 'w': 1920, 'h': 1080}

# ===== 로깅 설정 =====
LOG_LEVEL  = 'INFO'
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

# ===== 경로 =====
CONFIG_JSON_PATH = 'config.json'   # 사용자 설정 저장 파일
CAPTURE_DIR      = 'captures'      # 디버그 캡처 저장 폴더

# ===== 라이선스 시스템 (PHASE 2) =====
LICENSE_FILE_PATH = 'license.dat'   # 로컬 라이선스 토큰 저장 파일 (하드웨어ID 바인딩)

# 온라인 인증 서버 — PHASE 2 에서는 stub 으로 대체, 나중에 실제 서버 연결
LICENSE_SERVER_URL = 'https://example.com/api/license/verify'
LICENSE_SERVER_TIMEOUT = 5.0   # 온라인 검증 요청 타임아웃(초)

# 토큰 서명용 비밀키 — 실제 배포 시 서버만 알고 있어야 한다 (지금은 개발용 더미)
# 로컬 토큰 위변조 방지를 위한 HMAC-SHA256 서명에 사용한다.
LICENSE_SIGNING_SECRET = 'maple-macro-dev-secret-change-me'

# 개발용 강제 등급 — None 이면 실제 라이선스(license.dat) 검증 수행.
# 값('FREE'/'BASIC'/'PREMIUM')을 지정하면 검증을 건너뛰고 그 등급으로 강제한다.
# PHASE 2 개발 중에는 'PREMIUM' 으로 두어 전체 기능을 테스트하고,
# 실제 배포 시 반드시 None 으로 바꿔야 한다.
LICENSE_DEV_FORCE_TIER = 'PREMIUM'
