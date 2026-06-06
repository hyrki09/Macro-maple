"""PHASE 4 스킬 콤보 자동화 테스트 스크립트.

실제 게임/키 입력 없이 헤드리스로 검증한다.

  python test_phase4.py

검증 항목
  1) 저스펙 콤보가 설정된 키 순서대로 입력되는지
  2) 콤보 딜레이에 랜덤 지터(±SKILL_DELAY_JITTER)가 적용되는지
  3) 고스펙 콤보가 PREMIUM 에서만 실행되고 FREE/BASIC 은 차단되는지
     - 데코레이터 직접 호출 시 PermissionError
     - execute_skill_combo 디스패처는 denied=True 로 안전 처리
"""

import logging

import config
import input_controller
import macro_logic
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


def _force_tier(tier: str) -> None:
    """테스트용으로 현재 등급을 강제 설정한다 (캐시 직접 주입)."""
    license_manager._cached_tier = tier


def test_lowspec_order() -> None:
    """저스펙 콤보가 설정 순서대로 입력되는지 검증."""
    print("\n[1] 저스펙 콤보 키 순서")
    pressed = []
    original_press = input_controller.press_key
    original_sleep = macro_logic.time.sleep
    input_controller.press_key = lambda key, hold=None: pressed.append(key)
    macro_logic.time.sleep = lambda s: None   # 딜레이 건너뛰기
    try:
        mgr = macro_logic.SkillComboManager()
        r = mgr.execute_combo_lowspec()
        expected = [k for k, _ in config.SKILL_COMBO_MODE2]
        check("저스펙 실행 성공(ok)", r['ok'] and not r['denied'])
        check("입력 키 순서 일치", pressed == expected and r['keys'] == expected)
    finally:
        input_controller.press_key = original_press
        macro_logic.time.sleep = original_sleep


def test_jitter() -> None:
    """콤보 딜레이 지터가 기본값 주변에서 랜덤하게 변동하는지 검증."""
    print("\n[2] 딜레이 지터(_jittered_delay)")
    base = 0.5
    jitter = config.SKILL_DELAY_JITTER
    lo, hi = base * (1 - jitter), base * (1 + jitter)
    samples = [macro_logic._jittered_delay(base) for _ in range(200)]
    in_range = all(lo - 1e-9 <= s <= hi + 1e-9 for s in samples)
    varied = len(set(samples)) > 1   # 고정값이 아니라 실제로 변동
    check("지터 값이 기대 범위 내", in_range)
    check("지터가 고정값이 아님(랜덤)", varied)
    check("base 0 이면 딜레이 0", macro_logic._jittered_delay(0) == 0.0)


def test_highspec_license() -> None:
    """고스펙 콤보의 PREMIUM 등급 제한을 검증."""
    print("\n[3] 고스펙 콤보 라이선스 제한")
    pressed = []
    original_press = input_controller.press_key
    original_sleep = macro_logic.time.sleep
    original_tier = license_manager._cached_tier
    input_controller.press_key = lambda key, hold=None: pressed.append(key)
    macro_logic.time.sleep = lambda s: None
    try:
        mgr = macro_logic.SkillComboManager()
        expected = [k for k, _ in config.SKILL_COMBO_MODE1]

        # --- PREMIUM: 실행 가능 ---
        _force_tier('PREMIUM')
        pressed.clear()
        r_pre = mgr.execute_combo_highspec()
        check("PREMIUM 고스펙 실행 성공", r_pre['ok'] and pressed == expected)

        # --- PREMIUM 디스패처 경로 ---
        pressed.clear()
        r_disp = mgr.execute_skill_combo(config.SKILL_MODE_HIGHSPEC)
        check("PREMIUM 디스패처 실행 성공", r_disp['ok'] and not r_disp['denied'])

        # --- FREE: 데코레이터 직접 호출 → PermissionError ---
        _force_tier('FREE')
        pressed.clear()
        raised = False
        try:
            mgr.execute_combo_highspec()
        except PermissionError:
            raised = True
        check("FREE 고스펙 직접호출 차단(PermissionError)", raised and not pressed)

        # --- FREE: 디스패처는 denied=True 로 안전 처리 ---
        pressed.clear()
        r_free = mgr.execute_skill_combo(config.SKILL_MODE_HIGHSPEC)
        check("FREE 디스패처 거부(denied)",
              not r_free['ok'] and r_free['denied'] and not pressed)

        # --- BASIC: 고스펙 차단 ---
        _force_tier('BASIC')
        pressed.clear()
        r_basic = mgr.execute_skill_combo(config.SKILL_MODE_HIGHSPEC)
        check("BASIC 고스펙 거부(denied)",
              not r_basic['ok'] and r_basic['denied'] and not pressed)

        # --- BASIC: 저스펙은 허용 ---
        pressed.clear()
        r_basic_low = mgr.execute_skill_combo(config.SKILL_MODE_LOWSPEC)
        low_expected = [k for k, _ in config.SKILL_COMBO_MODE2]
        check("BASIC 저스펙 허용", r_basic_low['ok'] and pressed == low_expected)
    finally:
        input_controller.press_key = original_press
        macro_logic.time.sleep = original_sleep
        license_manager._cached_tier = original_tier


def test_unknown_mode() -> None:
    """알 수 없는 모드 입력 시 안전하게 실패하는지 검증."""
    print("\n[4] 알 수 없는 모드 처리")
    mgr = macro_logic.SkillComboManager()
    r = mgr.execute_skill_combo('nonexistent')
    check("미지의 모드 → ok=False, 예외 없음",
          not r['ok'] and not r['denied'] and r['keys'] == [])


def main() -> None:
    """전체 검증을 실행하고 결과를 출력한다."""
    print("===== PHASE 4 스킬 콤보 자동화 테스트 =====")
    test_lowspec_order()
    test_jitter()
    test_highspec_license()
    test_unknown_mode()
    print(f"\n===== 결과: {_passed} 통과 / {_failed} 실패 =====")
    raise SystemExit(1 if _failed else 0)


if __name__ == '__main__':
    main()
