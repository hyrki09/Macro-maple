"""PHASE 9 매매 루틴 테스트 스크립트.

실제 게임/키 입력/네트워크 없이 헤드리스로 검증한다.

  python test_phase9.py

검증 항목
  1) load_shop_config — 파일 없음/정상/손상 시 기본값·로드, 숫자 변환
  2) 단계 함수        — PREMIUM 에서 설정 키 시퀀스대로 입력
  3) buy_consumables — 구매 확정 키가 수량만큼 반복 입력
  4) run_routine     — 순서대로 4단계 실행, 비활성 시 skipped
  5) 라이선스 제한   — FREE/BASIC 은 denied=True, 키 입력 없음
  6) 주기(타이머)    — is_due/reset/mark_ran 동작
  7) main 연동       — 주기 도래 시 실행, PREMIUM 미만은 무실행
"""

import json
import logging
import os
import sys
import tempfile

# 콘솔 인코딩 문제(cp949) 방지 — stdout/stderr UTF-8 재설정
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import config
import input_controller
import shop_routine
from license.license_manager import license_manager

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


def _force_tier(tier: str) -> None:
    """테스트용으로 현재 등급을 강제 설정한다 (캐시 직접 주입)."""
    license_manager._cached_tier = tier


# ----- 키 입력/딜레이 가로채기 -----

class Patch:
    """press_key 와 time.sleep 을 가로채 키 입력만 기록하고 딜레이는 건너뛴다."""

    def __init__(self):
        self.pressed = []
        self._orig = {}

    def install(self):
        self._orig['press'] = input_controller.press_key
        self._orig['sleep'] = shop_routine.time.sleep
        input_controller.press_key = lambda key, hold=None: self.pressed.append(key)
        shop_routine.time.sleep = lambda s: None

    def restore(self):
        input_controller.press_key = self._orig['press']
        shop_routine.time.sleep = self._orig['sleep']


def test_load_config() -> None:
    """load_shop_config 파일 처리/숫자 변환 검증."""
    print("\n[1] load_shop_config")

    # (a) 파일 없음 → 기본값
    cfg = shop_routine.load_shop_config('___no_such___.json')
    check("파일 없으면 기본값", cfg['enabled'] is True
          and cfg['buy_quantity'] == config.SHOP_DEFAULTS['buy_quantity'])

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'config.json')
        # (b) 정상 로드 + 문자열 수량도 int 변환
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'shop': {'enabled': False, 'interval_sec': 60,
                                'buy_quantity': '15'}}, f)
        cfg = shop_routine.load_shop_config(p)
        check("정상 로드", cfg['enabled'] is False and cfg['interval_sec'] == 60.0
              and cfg['buy_quantity'] == 15)

        # (c) 블록 없음 → 기본값
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'other': 1}, f)
        cfg = shop_routine.load_shop_config(p)
        check("블록 없으면 기본값",
              cfg['buy_quantity'] == config.SHOP_DEFAULTS['buy_quantity'])

        # (d) 손상 JSON → 기본값(예외 안전)
        with open(p, 'w', encoding='utf-8') as f:
            f.write('{ broken')
        cfg = shop_routine.load_shop_config(p)
        check("손상 JSON 이면 기본값", cfg == dict(config.SHOP_DEFAULTS))


def test_steps() -> None:
    """각 단계가 PREMIUM 에서 설정 키 시퀀스대로 입력하는지 검증."""
    print("\n[2] 단계 키 시퀀스 (PREMIUM)")
    p = Patch(); p.install()
    orig_tier = license_manager._cached_tier
    _force_tier('PREMIUM')
    try:
        m = shop_routine.ShopRoutineManager()

        p.pressed.clear()
        m.go_to_shop()
        check("상점 이동 키 순서",
              p.pressed == [k for k, _ in config.SHOP_GO_SEQUENCE])

        p.pressed.clear()
        m.sell_items()
        check("판매 키 순서",
              p.pressed == [k for k, _ in config.SHOP_SELL_SEQUENCE])

        p.pressed.clear()
        m.return_to_hunting()
        check("복귀 키 순서",
              p.pressed == [k for k, _ in config.SHOP_RETURN_SEQUENCE])
    finally:
        p.restore()
        license_manager._cached_tier = orig_tier


def test_buy() -> None:
    """buy_consumables 가 구매 확정 키를 수량만큼 반복하는지 검증."""
    print("\n[3] buy_consumables 수량 반복")
    p = Patch(); p.install()
    orig_tier = license_manager._cached_tier
    _force_tier('PREMIUM')
    try:
        m = shop_routine.ShopRoutineManager()
        m.buy_quantity = 5
        p.pressed.clear()
        m.buy_consumables()
        open_keys = [k for k, _ in config.SHOP_BUY_OPEN_SEQUENCE]
        confirms = p.pressed[len(open_keys):]
        check("구매 탭 열기 키 입력", p.pressed[:len(open_keys)] == open_keys)
        check("구매 확정 키 5회 반복",
              confirms == [config.SHOP_BUY_CONFIRM_KEY] * 5)

        # 수량 0 → 구매 확정 입력 없음
        p.pressed.clear()
        m.buy_consumables(quantity=0)
        check("수량 0 이면 확정 입력 없음",
              p.pressed == open_keys)
    finally:
        p.restore()
        license_manager._cached_tier = orig_tier


def test_run_routine() -> None:
    """run_routine 순서/비활성 처리 검증."""
    print("\n[4] run_routine 전체 흐름")
    p = Patch(); p.install()
    orig_tier = license_manager._cached_tier
    _force_tier('PREMIUM')
    try:
        m = shop_routine.ShopRoutineManager()
        m.enabled = True
        m.buy_quantity = 2
        p.pressed.clear()
        r = m.run_routine()
        check("루틴 성공(ok)", r['ok'] and not r['denied'])
        check("4단계 모두 성공",
              r['steps'] == {'go': True, 'sell': True, 'buy': True, 'return': True})
        # 이동→판매→구매→복귀 순서대로 키가 누적됐는지(첫 키 = 이동 첫 키)
        check("이동 단계가 가장 먼저",
              p.pressed[0] == config.SHOP_GO_SEQUENCE[0][0])

        # 비활성 → skipped, 키 입력 없음
        m.enabled = False
        p.pressed.clear()
        r2 = m.run_routine()
        check("비활성 시 skipped + 무입력",
              r2['ok'] and r2['skipped'] and not p.pressed)
    finally:
        p.restore()
        license_manager._cached_tier = orig_tier


def test_license() -> None:
    """FREE/BASIC 등급에서 매매가 차단(denied)되는지 검증."""
    print("\n[5] 라이선스 제한")
    p = Patch(); p.install()
    orig_tier = license_manager._cached_tier
    try:
        m = shop_routine.ShopRoutineManager()
        m.enabled = True

        # FREE: 단계 직접 호출 → PermissionError
        _force_tier('FREE')
        p.pressed.clear()
        raised = False
        try:
            m.go_to_shop()
        except PermissionError:
            raised = True
        check("FREE 단계 직접호출 차단(PermissionError)", raised and not p.pressed)

        # FREE: run_routine → denied, 키 입력 없음
        p.pressed.clear()
        r_free = m.run_routine()
        check("FREE run_routine 거부(denied)",
              not r_free['ok'] and r_free['denied'] and not p.pressed)

        # BASIC: 동일하게 거부
        _force_tier('BASIC')
        p.pressed.clear()
        r_basic = m.run_routine()
        check("BASIC run_routine 거부(denied)",
              not r_basic['ok'] and r_basic['denied'] and not p.pressed)
    finally:
        p.restore()
        license_manager._cached_tier = orig_tier


def test_timer() -> None:
    """is_due / reset / mark_ran 주기 제어 검증."""
    print("\n[6] 주기(타이머)")
    m = shop_routine.ShopRoutineManager()
    m.enabled = True
    m.interval = 100.0

    # 첫 호출 → 기준점만 잡고 False
    check("첫 is_due 는 False", m.is_due(now=0.0) is False)
    # 주기 미달 → False
    check("주기 미달 False", m.is_due(now=50.0) is False)
    # 주기 도달 → True
    check("주기 도달 True", m.is_due(now=100.0) is True)
    # 실행 표시 후 다시 미달
    m.mark_ran(now=100.0)
    check("mark_ran 후 미달 False", m.is_due(now=150.0) is False)
    check("mark_ran 후 도달 True", m.is_due(now=200.0) is True)

    # 비활성이면 항상 False
    m.enabled = False
    check("비활성 시 항상 False", m.is_due(now=10_000.0) is False)

    # reset 후 기준점 재설정
    m.enabled = True
    m.reset(now=500.0)
    check("reset 직후 미달 False", m.is_due(now=550.0) is False)


def test_main_integration() -> None:
    """main 의 _check_shop 가 주기/등급에 따라 동작하는지 검증."""
    print("\n[7] main 연동")
    import main
    orig_tier = license_manager._cached_tier
    orig_notify = main.telegram_bot.notify_shop
    notified = []
    main.telegram_bot.notify_shop = lambda: notified.append(True)
    try:
        app = main.MacroApp.__new__(main.MacroApp)  # __init__ 우회

        ran = []

        class FakeShop:
            def __init__(self):
                self._due = True

            def is_due(self):
                return self._due

            def run_routine(self):
                ran.append(True)
                return {'ok': True, 'denied': False, 'skipped': False, 'steps': {}}

            def mark_ran(self):
                pass
        app.shop = FakeShop()

        # PREMIUM + due → 실행 + 알림
        _force_tier('PREMIUM')
        app._check_shop()
        check("PREMIUM 주기 도래 시 실행", ran and notified)

        # PREMIUM 이지만 주기 미달 → 무실행
        ran.clear(); notified.clear()
        app.shop._due = False
        app._check_shop()
        check("주기 미달 시 무실행", not ran)

        # FREE → 무실행(전용 기능)
        ran.clear()
        app.shop._due = True
        _force_tier('FREE')
        app._check_shop()
        check("FREE 는 무실행", not ran)
    finally:
        main.telegram_bot.notify_shop = orig_notify
        license_manager._cached_tier = orig_tier


def main() -> None:
    """헤드리스 자동 검증 실행."""
    print("===== PHASE 9 매매 루틴 테스트 =====")
    test_load_config()
    test_steps()
    test_buy()
    test_run_routine()
    test_license()
    test_timer()
    test_main_integration()
    print(f"\n===== 결과: {_passed} 통과 / {_failed} 실패 =====")
    sys.exit(_failed)


if __name__ == '__main__':
    main()
