"""PHASE 3 HP/MP 포션 자동 사용 테스트 스크립트.

두 가지 모드를 지원한다.

1) 기본(자동 검증) 모드:  python test_phase3.py
   - 실제 게임 없이 합성 이미지로 get_bar_ratio 색상 인식 검증
   - PotionManager 의 임계값 비교 / 쿨다운 로직 검증
   - 화면이나 키 입력 없이 헤드리스로 동작

2) 라이브 모드:  python test_phase3.py --live
   - 실제 게임 화면을 읽어 현재 HP%, MP% 를 1초마다 콘솔에 출력
   - q 키(또는 Ctrl+C)로 종료
   - HP_BAR_REGION / MP_BAR_REGION / 색상 범위 보정에 사용
"""

import logging
import sys
import time

# 콘솔 기본 인코딩(예: Windows cp949)이 유니코드 문자(≈, ± 등)를 출력하지 못해
# UnicodeEncodeError 로 죽는 것을 막기 위해 stdout/stderr 을 UTF-8 로 재설정한다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        # 일부 환경(reconfigure 미지원 스트림)에서는 무시
        pass

import numpy as np

import config
import macro_logic
import screen_capture

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


def _make_bar(width: int, height: int, fill_ratio: float, bgr: tuple) -> np.ndarray:
    """가로 바 합성 이미지를 만든다. 왼쪽 fill_ratio 만큼 색을 채운다.

    Args:
        width: 바 폭(px).
        height: 바 높이(px).
        fill_ratio: 채울 비율(0~1).
        bgr: 채움 색 (B, G, R).

    Returns:
        (height, width, 3) BGR 이미지. 채워지지 않은 부분은 어두운 회색.
    """
    img = np.full((height, width, 3), 30, dtype=np.uint8)   # 빈 부분: 어두운 회색
    fill_w = int(width * fill_ratio)
    img[:, :fill_w] = bgr
    return img


def test_bar_ratio() -> None:
    """합성 이미지로 HP(빨강)/MP(파랑) 비율 인식 정확도 검증."""
    print("\n[1] get_bar_ratio 색상 인식 (합성 이미지)")
    if not screen_capture._CV2_AVAILABLE:
        check("opencv 사용 가능", False)
        return

    region = {'x': 0, 'y': 0, 'w': 200, 'h': 20}
    original = screen_capture.capture_region
    try:
        # --- HP 빨강 60% ---
        red = (0, 0, 255)
        screen_capture.capture_region = lambda r: _make_bar(200, 20, 0.60, red)
        hp = screen_capture.get_bar_ratio(region, config.HP_COLOR_RANGES)
        print(f"  HP 60% 합성 → 측정 {hp:.1f}%")
        check("HP 60% 근사(±5)", hp is not None and abs(hp - 60) <= 5)

        # --- MP 파랑 25% ---
        blue = (255, 0, 0)
        screen_capture.capture_region = lambda r: _make_bar(200, 20, 0.25, blue)
        mp = screen_capture.get_bar_ratio(region, config.MP_COLOR_RANGES)
        print(f"  MP 25% 합성 → 측정 {mp:.1f}%")
        check("MP 25% 근사(±5)", mp is not None and abs(mp - 25) <= 5)

        # --- 빈 바(0%) ---
        screen_capture.capture_region = lambda r: _make_bar(200, 20, 0.0, red)
        empty = screen_capture.get_bar_ratio(region, config.HP_COLOR_RANGES)
        check("빈 바 ≈ 0%", empty is not None and empty <= 5)

        # --- 색이 다르면(파랑인데 HP 빨강으로 측정) 거의 0 ---
        screen_capture.capture_region = lambda r: _make_bar(200, 20, 1.0, blue)
        wrong = screen_capture.get_bar_ratio(region, config.HP_COLOR_RANGES)
        check("색상 불일치 시 ≈ 0%", wrong is not None and wrong <= 5)
    finally:
        screen_capture.capture_region = original


def test_potion_logic() -> None:
    """임계값 비교 + 포션 키 입력 + 쿨다운 로직 검증."""
    print("\n[2] PotionManager 임계값/쿨다운 로직")

    # input_controller.press_key 를 가로채 호출 키를 기록
    pressed = []
    import input_controller
    original_press = input_controller.press_key
    original_hp = screen_capture.get_hp_ratio
    original_mp = screen_capture.get_mp_ratio
    macro_logic.input_controller.press_key = lambda key, hold=None: pressed.append(key)

    try:
        mgr = macro_logic.PotionManager()

        # HP 30%(<=50 임계) / MP 80%(>30 임계) → HP만 사용
        screen_capture.get_hp_ratio = lambda debug=False: 30.0
        screen_capture.get_mp_ratio = lambda debug=False: 80.0
        r1 = mgr.check_and_use_potion()
        check("HP 낮음 → HP 포션 사용", r1['hp_used'] and config.HP_POTION_KEY in pressed)
        check("MP 충분 → MP 포션 미사용", not r1['mp_used'])

        # 즉시 재호출 → HP 쿨다운으로 미사용
        pressed.clear()
        r2 = mgr.check_and_use_potion()
        check("쿨다운 중 HP 포션 미사용", not r2['hp_used'] and config.HP_POTION_KEY not in pressed)

        # 쿨다운 지난 것처럼 마지막 사용 시각을 과거로 밀고 재호출 → 사용
        pressed.clear()
        mgr._last_hp_time -= (config.HP_POTION_COOLDOWN + 1)
        r3 = mgr.check_and_use_potion()
        check("쿨다운 경과 후 HP 포션 재사용", r3['hp_used'] and config.HP_POTION_KEY in pressed)

        # HP/MP 모두 낮음 → 둘 다 사용 (새 매니저로 쿨다운 초기화)
        pressed.clear()
        mgr2 = macro_logic.PotionManager()
        screen_capture.get_hp_ratio = lambda debug=False: 10.0
        screen_capture.get_mp_ratio = lambda debug=False: 5.0
        r4 = mgr2.check_and_use_potion()
        check("HP/MP 모두 낮음 → 둘 다 사용",
              r4['hp_used'] and r4['mp_used']
              and config.HP_POTION_KEY in pressed and config.MP_POTION_KEY in pressed)

        # 측정 실패(None) → 포션 미사용 (예외 없이 안전)
        pressed.clear()
        mgr3 = macro_logic.PotionManager()
        screen_capture.get_hp_ratio = lambda debug=False: None
        screen_capture.get_mp_ratio = lambda debug=False: None
        r5 = mgr3.check_and_use_potion()
        check("측정 실패 시 미사용/예외없음",
              not r5['hp_used'] and not r5['mp_used'] and not pressed)
    finally:
        input_controller.press_key = original_press
        macro_logic.input_controller.press_key = original_press
        screen_capture.get_hp_ratio = original_hp
        screen_capture.get_mp_ratio = original_mp


def run_live() -> None:
    """실제 화면을 읽어 HP%/MP% 를 1초마다 출력한다. q/Ctrl+C 로 종료."""
    print("===== 라이브 모드 — HP%/MP% 실시간 출력 (q 또는 Ctrl+C 종료) =====")
    try:
        import keyboard
        has_keyboard = True
    except Exception:
        has_keyboard = False
        print("  (keyboard 모듈 없음 — Ctrl+C 로만 종료 가능)")

    try:
        while True:
            hp = screen_capture.get_hp_ratio(debug=False)
            mp = screen_capture.get_mp_ratio(debug=False)
            hp_s = f"{hp:5.1f}%" if hp is not None else "  N/A"
            mp_s = f"{mp:5.1f}%" if mp is not None else "  N/A"
            print(f"  HP {hp_s}   MP {mp_s}")
            if has_keyboard and keyboard.is_pressed('q'):
                print("  q 입력 — 종료")
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n  Ctrl+C — 종료")


def main() -> None:
    """인자에 따라 자동 검증 또는 라이브 모드를 실행한다."""
    if '--live' in sys.argv:
        run_live()
        return

    print("===== PHASE 3 HP/MP 포션 자동 사용 테스트 =====")
    test_bar_ratio()
    test_potion_logic()
    print(f"\n===== 결과: {_passed} 통과 / {_failed} 실패 =====")
    print("실게임 보정은 'python test_phase3.py --live' 로 확인하세요.")
    raise SystemExit(1 if _failed else 0)


if __name__ == '__main__':
    main()
