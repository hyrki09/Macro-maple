"""PHASE 7 상태 감시 시스템 테스트 스크립트.

실제 게임/화면/키 입력 없이 헤드리스로 검증한다.

  python test_phase7.py

검증 항목
  1) detect_position_stuck — 움직이면 리셋, 장시간 정지면 감지, None 안전
  2) detect_position_loop  — 표본 부족/정상 스윕은 무탐, 좁은 좌표 반복은 감지
  3) detect_town/detect_jail — 템플릿 매칭 True/False, 템플릿 없으면 False
  4) check() — 종합 판정(alert/reasons), 주기 미달 시 skipped
  5) reset() — 누적 상태 초기화
  6) main 연동 — alert 시 매크로 자동 정지(running=False)
"""

import logging
import sys

# 콘솔 인코딩 문제(cp949) 방지 — stdout/stderr UTF-8 재설정
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import config
import monitor
import screen_capture

logging.basicConfig(level=logging.ERROR, format='  %(levelname)s: %(message)s')

_passed = 0
_failed = 0


def check(name: str, condition: bool) -> None:
    """단일 검사 결과를 출력하고 카운터를 갱신한다."""
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}")


# ----- 공용 모킹 헬퍼 -----

class Mocks:
    """미니맵 좌표/템플릿/캡처/매칭을 가로채는 테스트 더블 묶음."""

    def __init__(self):
        self.pos = None              # get_character_position 반환값
        self.templates = set()       # load_template 이 '존재'로 칠 경로 집합
        self.matches = set()         # find_template 이 매칭 성공으로 칠 경로 집합
        self._orig = {}

    def _load_template(self, path, use_cache=True):
        # 등록된 경로는 더미 템플릿(경로 문자열)을 반환, 아니면 None(파일 없음)
        return path if path in self.templates else None

    def _capture_region(self, region):
        return 'SCREEN'   # 더미 화면 — None 아니기만 하면 됨

    def _find_template(self, image, template, threshold=None, debug=False):
        # template 은 _load_template 이 돌려준 경로 문자열
        if template in self.matches:
            return {'score': 0.95, 'top_left': (0, 0),
                    'center': (1, 1), 'size': (1, 1)}
        return None

    def _get_pos(self, *a, **k):
        return self.pos

    def install(self):
        self._orig['pos'] = screen_capture.get_character_position
        self._orig['load'] = screen_capture.load_template
        self._orig['capture'] = screen_capture.capture_region
        self._orig['find'] = screen_capture.find_template
        screen_capture.get_character_position = self._get_pos
        screen_capture.load_template = self._load_template
        screen_capture.capture_region = self._capture_region
        screen_capture.find_template = self._find_template

    def restore(self):
        screen_capture.get_character_position = self._orig['pos']
        screen_capture.load_template = self._orig['load']
        screen_capture.capture_region = self._orig['capture']
        screen_capture.find_template = self._orig['find']


def test_stuck() -> None:
    """detect_position_stuck 정지 판정 검증."""
    print("\n[1] detect_position_stuck")
    sm = monitor.StateMonitor()
    # 첫 표본은 기준만 세움
    check("첫 표본은 정지 아님", sm.detect_position_stuck((100, 50), now=0.0) is False)
    # 임계 이내 미동 + 시간 경과 → 정지
    over = config.STUCK_TIME_THRESHOLD + 1.0
    check("미동 + 임계 시간 경과 → 정지",
          sm.detect_position_stuck((101, 50), now=over) is True)

    # 움직이면 타이머 리셋되어 정지 아님
    sm2 = monitor.StateMonitor()
    sm2.detect_position_stuck((100, 50), now=0.0)
    moved_x = 100 + config.STUCK_POS_TOLERANCE + 5
    check("충분히 움직이면 정지 아님",
          sm2.detect_position_stuck((moved_x, 50), now=over) is False)
    # 리셋된 시점 기준으로 다시 시간 경과해야 정지
    check("리셋 직후 같은 시각은 정지 아님",
          sm2.detect_position_stuck((moved_x, 50), now=over) is False)

    # None 좌표는 안전하게 False
    sm3 = monitor.StateMonitor()
    check("좌표 None 이면 False", sm3.detect_position_stuck(None, now=over) is False)


def test_loop() -> None:
    """detect_position_loop 반복 좌표 판정 검증."""
    print("\n[2] detect_position_loop")

    # (a) 표본 부족 — 큐가 안 차면 무탐
    sm = monitor.StateMonitor()
    res = [sm.detect_position_loop((10, 10)) for _ in range(config.LOOP_HISTORY_SIZE - 1)]
    check("표본 부족 시 무탐", not any(res))

    # (b) 정상 좌우 스윕 — x 가 넓게 흩어지면 무탐
    sm2 = monitor.StateMonitor()
    last = False
    tol = config.LOOP_POS_TOLERANCE
    for i in range(config.LOOP_HISTORY_SIZE):
        # 매 표본 칸이 달라지도록 x 를 tol 이상씩 이동
        last = sm2.detect_position_loop((10 + i * tol * 2, 50))
    check("넓게 이동하는 정상 스윕은 무탐", last is False)

    # (c) 같은 좁은 좌표 반복 — 임계 횟수 넘으면 감지
    sm3 = monitor.StateMonitor()
    last = False
    for _ in range(config.LOOP_HISTORY_SIZE):
        last = sm3.detect_position_loop((77, 88))
    check("같은 좌표 반복 → 감지", last is True)

    # (d) None 좌표는 안전하게 False
    sm4 = monitor.StateMonitor()
    check("좌표 None 이면 False", sm4.detect_position_loop(None) is False)


def test_town_jail() -> None:
    """detect_town / detect_jail 템플릿 매칭 검증."""
    print("\n[3] detect_town / detect_jail")
    m = Mocks(); m.install()
    try:
        sm = monitor.StateMonitor()
        # 템플릿 자체가 없으면 False
        check("마을 템플릿 없으면 False", sm.detect_town() is False)
        check("감옥 템플릿 없으면 False", sm.detect_jail() is False)

        # 템플릿은 있으나 매칭 실패 → False
        m.templates = {config.TOWN_TEMPLATE_PATH, config.JAIL_TEMPLATE_PATH}
        check("템플릿 있고 매칭 실패면 False", sm.detect_town() is False)

        # 템플릿 있고 매칭 성공 → True
        m.matches = {config.TOWN_TEMPLATE_PATH}
        check("마을 매칭 성공 → True", sm.detect_town() is True)
        check("감옥은 매칭 미등록 → False", sm.detect_jail() is False)
        m.matches = {config.JAIL_TEMPLATE_PATH}
        check("감옥 매칭 성공 → True", sm.detect_jail() is True)
    finally:
        m.restore()


def test_check_integration() -> None:
    """check() 종합 판정과 주기 제어 검증."""
    print("\n[4] check() 종합 판정")
    m = Mocks(); m.install()
    try:
        # (a) 정상 — 위치 정상, 템플릿 없음 → alert 없음
        sm = monitor.StateMonitor()
        m.pos = (100, 50)
        r = sm.check(now=0.0)
        check("정상 시 alert 없음", r['alert'] is False and r['reasons'] == [])
        check("정상 시 pos 채워짐", r['pos'] == (100, 50))

        # (b) 주기 미달 → skipped
        r2 = sm.check(now=config.MONITOR_CHECK_INTERVAL / 2)
        check("주기 미달이면 skipped", r2['skipped'] is True and r2['alert'] is False)

        # (c) 마을 감지 → alert + reasons 에 town
        m.templates = {config.TOWN_TEMPLATE_PATH}
        m.matches = {config.TOWN_TEMPLATE_PATH}
        r3 = sm.check(now=config.MONITOR_CHECK_INTERVAL + 1.0)
        check("마을 감지 시 alert", r3['alert'] is True)
        check("reasons 에 town 포함", 'town' in r3['reasons'])
    finally:
        m.restore()


def test_reset() -> None:
    """reset() 이 누적 상태(정지/반복/주기)를 비우는지 검증."""
    print("\n[5] reset()")
    sm = monitor.StateMonitor()
    sm.detect_position_stuck((10, 10), now=0.0)
    sm.detect_position_loop((10, 10))
    sm._last_check_time = 5.0
    sm.reset()
    check("정지 기준 초기화", sm._last_pos is None and sm._last_move_time is None)
    check("반복 기록 초기화", len(sm._pos_history) == 0)
    check("주기 시각 초기화", sm._last_check_time is None)


def test_main_autostop() -> None:
    """main 의 _check_monitor 가 alert 시 매크로를 자동 정지하는지 검증."""
    print("\n[6] main 연동 — 자동 정지")
    import main

    app = main.MacroApp.__new__(main.MacroApp)   # __init__ 우회(핫키/헌터 생성 회피)
    app.running = True

    # alert 를 강제로 내는 가짜 monitor 주입
    class FakeMonitor:
        def check(self):
            return {'alert': True, 'reasons': ['town'], 'pos': None,
                    'stuck': False, 'loop': False, 'town': True,
                    'jail': False, 'skipped': False}
    app.monitor = FakeMonitor()
    app._check_monitor()
    check("alert 감지 시 running=False", app.running is False)

    # alert 없으면 계속 동작
    app.running = True

    class FakeOk:
        def check(self):
            return {'alert': False, 'reasons': [], 'pos': (1, 1),
                    'stuck': False, 'loop': False, 'town': False,
                    'jail': False, 'skipped': False}
    app.monitor = FakeOk()
    app._check_monitor()
    check("정상 시 running 유지", app.running is True)


def main() -> None:
    """헤드리스 자동 검증 실행."""
    print("===== PHASE 7 상태 감시 시스템 테스트 =====")
    test_stuck()
    test_loop()
    test_town_jail()
    test_check_integration()
    test_reset()
    test_main_autostop()
    print(f"\n===== 결과: {_passed} 통과 / {_failed} 실패 =====")
    sys.exit(_failed)


if __name__ == '__main__':
    main()
