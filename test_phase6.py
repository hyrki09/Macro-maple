"""PHASE 6 패턴 방식 자동 이동 테스트 스크립트.

실제 게임/키 입력/화면 없이 헤드리스로 검증한다.

  python test_phase6.py

검증 항목
  1) BaseHunter 인터페이스 (find_monsters/decide_action 상태 전이)
  2) move_left_right 가 방향에 맞는 키를 hold 와 함께 누르는지
  3) _sweep 이 스킬 콤보 호출 + 방향 전환 + 카운터 증가를 하는지
  4) move_to_floor 가 미니맵 층 판정으로 도달/실패를 처리하는지
  5) _change_floor 실패 시 floor_recovery 가 호출되는지
  6) run_loop 가 max_steps / should_continue 를 지키는지
  7) FREE 등급에서도 패턴 사냥(좌우 이동)이 동작하는지
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
import input_controller
import macro_logic
import screen_capture
from hunting import base_hunter
from hunting.pattern_hunter import PatternHunter
from license.license_manager import license_manager

logging.basicConfig(level=logging.WARNING, format='  %(levelname)s: %(message)s')

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
    """press_key/스킬콤보/미니맵/sleep 을 가로채는 테스트 더블 묶음."""

    def __init__(self):
        self.pressed = []          # [(key, hold), ...]
        self.combo_calls = []      # 스킬 콤보 호출 모드 목록
        self.positions = []        # get_character_position 이 차례로 돌려줄 좌표 큐
        self.default_pos = None    # 큐가 비면 돌려줄 기본 좌표
        self._orig = {}

    def _next_pos(self, *a, **k):
        if self.positions:
            return self.positions.pop(0)
        return self.default_pos

    def install(self):
        # pattern_hunter/base_hunter 는 'import time' 이라 같은 time 모듈을 공유한다.
        # time.sleep 을 no-op 으로 바꿔 대기 없이 빠르게 검증한다.
        self._orig['press'] = input_controller.press_key
        self._orig['combo'] = macro_logic.execute_skill_combo
        self._orig['pos'] = screen_capture.get_character_position
        self._orig['sleep'] = base_hunter.time.sleep

        input_controller.press_key = lambda key, hold=None: self.pressed.append((key, hold))
        macro_logic.execute_skill_combo = lambda mode=None: (
            self.combo_calls.append(mode) or {'mode': mode, 'ok': True, 'denied': False, 'keys': []}
        )
        screen_capture.get_character_position = self._next_pos
        base_hunter.time.sleep = lambda s: None

    def restore(self):
        input_controller.press_key = self._orig['press']
        macro_logic.execute_skill_combo = self._orig['combo']
        screen_capture.get_character_position = self._orig['pos']
        base_hunter.time.sleep = self._orig['sleep']

    @property
    def keys(self):
        return [k for k, _ in self.pressed]


# 미니맵 층 좌표 — y ≤ FLOOR2_Y_THRESHOLD 면 2층
_FLOOR2_POS = (90, 20)
_FLOOR1_POS = (90, 80)


def test_interface() -> None:
    """find_monsters/decide_action 상태 전이를 검증."""
    print("\n[1] BaseHunter 인터페이스")
    h = PatternHunter()
    check("find_monsters() == []", h.find_monsters() == [])
    check("초기 decide_action == 'sweep'", h.decide_action([]) == 'sweep')
    h._sweeps_done = config.SWEEPS_PER_FLOOR
    check("스윕 소진 후 'change_floor'", h.decide_action([]) == 'change_floor')


def test_move_left_right() -> None:
    """방향에 맞는 키를 hold 와 함께 누르는지 검증."""
    print("\n[2] move_left_right")
    m = Mocks(); m.install()
    try:
        h = PatternHunter()
        d = h.move_left_right('right', hold=0.7)
        check("right → 오른쪽 키", m.keys == [config.MOVE_RIGHT_KEY] and d == 'right')
        check("hold 값 전달", m.pressed[0][1] == 0.7)

        m.pressed.clear()
        h.move_left_right('left')
        check("left → 왼쪽 키", m.keys == [config.MOVE_LEFT_KEY])
        check("hold None 시 범위 내 랜덤",
              config.MOVE_HOLD_MIN <= m.pressed[0][1] <= config.MOVE_HOLD_MAX)
    finally:
        m.restore()


def test_sweep() -> None:
    """_sweep: 이동 + 스킬콤보 + 방향전환 + 카운터 증가."""
    print("\n[3] _sweep 동작")
    m = Mocks(); m.install()
    try:
        h = PatternHunter()   # 시작 방향 right
        h._sweep()
        check("이동 키 입력됨", m.keys == [config.MOVE_RIGHT_KEY])
        check("스킬 콤보 1회 호출", len(m.combo_calls) == 1)
        check("방향 전환(right→left)", h._direction == 'left')
        check("스윕 카운터 증가", h._sweeps_done == 1)
    finally:
        m.restore()


def test_move_to_floor() -> None:
    """move_to_floor 도달/실패 처리 검증."""
    print("\n[4] move_to_floor")
    # (a) 이미 목표 층 → 점프 없이 True
    m = Mocks(); m.install()
    try:
        h = PatternHunter()
        m.positions = [_FLOOR2_POS]
        ok = h.move_to_floor(2)
        check("이미 2층이면 즉시 True", ok is True)
        check("점프 입력 없음", config.JUMP_KEY not in m.keys)
    finally:
        m.restore()

    # (b) 1층 → 점프 후 2층 도달
    m = Mocks(); m.install()
    try:
        h = PatternHunter()
        m.positions = [_FLOOR1_POS, _FLOOR2_POS]   # 한 번 점프 후 도착
        ok = h.move_to_floor(2)
        check("점프 후 2층 도달 True", ok is True)
        check("위층 이동 키(UP+JUMP) 입력",
              config.UP_KEY in m.keys and config.JUMP_KEY in m.keys)
    finally:
        m.restore()

    # (c) 계속 1층 → 실패 False
    m = Mocks(); m.install()
    try:
        h = PatternHunter()
        m.default_pos = _FLOOR1_POS   # 항상 1층
        ok = h.move_to_floor(2)
        check("도달 못하면 False", ok is False)
        check("시도 횟수만큼 점프", m.keys.count(config.JUMP_KEY) == config.FLOOR_MOVE_ATTEMPTS)
    finally:
        m.restore()


def test_change_floor_recovery() -> None:
    """_change_floor 실패 시 floor_recovery 호출, 성공 시 층 전환."""
    print("\n[5] _change_floor / floor_recovery")
    # (a) 실패 → 복구 호출
    m = Mocks(); m.install()
    try:
        h = PatternHunter()
        h._target_floor = 1
        h._sweeps_done = config.SWEEPS_PER_FLOOR
        recovery_called = {'n': 0}
        h.move_to_floor = lambda floor: False
        orig_recovery = h.floor_recovery
        h.floor_recovery = lambda: recovery_called.__setitem__('n', recovery_called['n'] + 1)
        h._change_floor()
        check("이동 실패 시 floor_recovery 호출", recovery_called['n'] == 1)
        check("실패 시 층 유지(1)", h._target_floor == 1)
        check("스윕 카운터 리셋", h._sweeps_done == 0)
    finally:
        m.restore()

    # (b) 성공 → 층 전환, 복구 미호출
    m = Mocks(); m.install()
    try:
        h = PatternHunter()
        h._target_floor = 1
        recovery_called = {'n': 0}
        h.move_to_floor = lambda floor: True
        h.floor_recovery = lambda: recovery_called.__setitem__('n', recovery_called['n'] + 1)
        h._change_floor()
        check("이동 성공 시 층 전환(1→2)", h._target_floor == 2)
        check("성공 시 복구 미호출", recovery_called['n'] == 0)
    finally:
        m.restore()


def test_run_loop() -> None:
    """run_loop 가 max_steps / should_continue 를 지키는지 검증."""
    print("\n[6] run_loop 제어")
    m = Mocks(); m.install()
    try:
        h = PatternHunter()
        m.default_pos = _FLOOR1_POS
        steps = h.run_loop(max_steps=5)
        check("max_steps 만큼 실행", steps == 5)

        steps0 = h.run_loop(should_continue=lambda: False, max_steps=10)
        check("should_continue False 면 0회", steps0 == 0)
    finally:
        m.restore()


def test_free_tier() -> None:
    """FREE 등급에서도 패턴 좌우 이동이 동작하는지 검증."""
    print("\n[7] FREE 등급 패턴 사냥")
    m = Mocks(); m.install()
    orig_tier = license_manager._cached_tier
    try:
        license_manager._cached_tier = 'FREE'
        h = PatternHunter()
        h._sweep()
        check("FREE 도 좌우 이동 입력됨", m.keys == [config.MOVE_RIGHT_KEY])
        check("FREE 스킬 콤보 호출됨(저스펙)", len(m.combo_calls) == 1)
    finally:
        license_manager._cached_tier = orig_tier
        m.restore()


def main() -> None:
    """헤드리스 자동 검증 실행."""
    print("===== PHASE 6 패턴 방식 자동 이동 테스트 =====")
    test_interface()
    test_move_left_right()
    test_sweep()
    test_move_to_floor()
    test_change_floor_recovery()
    test_run_loop()
    test_free_tier()
    print(f"\n===== 결과: {_passed} 통과 / {_failed} 실패 =====")
    sys.exit(_failed)


if __name__ == '__main__':
    main()
