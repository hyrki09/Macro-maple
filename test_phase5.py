"""PHASE 5 미니맵 좌표 인식 테스트 스크립트.

두 가지 모드를 지원한다.

1) 기본(자동 검증) 모드:  python test_phase5.py
   - 실제 게임 없이 합성 미니맵/템플릿으로 검증
   - find_template 매칭 정확도, get_character_position 좌표,
     템플릿 없을 때/매칭 실패 시 None 처리 검증
   - 화면이나 키 입력 없이 헤드리스로 동작

2) 라이브 모드:  python test_phase5.py --live
   - 실제 게임 미니맵(config.MINIMAP_REGION)을 읽어
     캐릭터 좌표를 1초마다 콘솔에 출력
   - Ctrl+C 로 종료
   - assets/minimap/char_dot.png 템플릿과 MINIMAP_REGION 보정에 사용
"""

import logging
import sys
import time

# 콘솔 기본 인코딩(예: Windows cp949)이 유니코드 문자를 출력하지 못해
# UnicodeEncodeError 로 죽는 것을 막기 위해 stdout/stderr 을 UTF-8 로 재설정한다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import numpy as np

import config
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


def _make_dot_template(size: int = 9) -> np.ndarray:
    """캐릭터 점 합성 템플릿 BGR 배열을 만든다.

    어두운 테두리 + 밝은 노란 중심으로 구성해 내부 명암 대비(분산)를 준다.
    (TM_CCOEFF_NORMED 는 평균을 빼고 정규화하므로 단색 패치는 매칭이 불안정하다.
     실제 게임의 캐릭터 점도 어두운 미니맵 위 밝은 점이라 대비가 있다.)
    """
    tmpl = np.full((size, size, 3), 30, dtype=np.uint8)   # 어두운 테두리
    c0, c1 = size // 3, size - size // 3
    tmpl[c0:c1, c0:c1] = (0, 220, 220)                    # BGR: 밝은 노란 중심
    return tmpl


def _make_minimap(dot_xy: tuple | None, w: int = 180, h: int = 120,
                  dot: np.ndarray | None = None) -> np.ndarray:
    """어두운 배경 미니맵에 dot_xy(좌상단) 위치로 점을 박은 합성 이미지를 만든다.

    Args:
        dot_xy: 점 좌상단 (x, y). None 이면 점 없는 빈 미니맵.
        w, h: 미니맵 크기.
        dot: 박을 점 템플릿. None 이면 _make_dot_template() 사용.
    """
    img = np.full((h, w, 3), 30, dtype=np.uint8)   # 어두운 회색 배경
    if dot_xy is not None:
        if dot is None:
            dot = _make_dot_template()
        dh, dw = dot.shape[:2]
        x, y = dot_xy
        img[y:y + dh, x:x + dw] = dot
    return img


def test_find_template() -> None:
    """find_template 이 점 위치를 정확히 찾는지 검증."""
    print("\n[1] find_template 매칭 정확도")
    dot = _make_dot_template(8)
    minimap = _make_minimap((50, 30), dot=dot)   # 점 좌상단 (50,30) → 중심 (54,34)

    m = screen_capture.find_template(minimap, dot, threshold=0.7)
    check("점을 찾음(None 아님)", m is not None)
    if m is not None:
        cx, cy = m['center']
        check(f"중심 x≈54 (측정 {cx})", abs(cx - 54) <= 2)
        check(f"중심 y≈34 (측정 {cy})", abs(cy - 34) <= 2)
        check("매칭 점수 높음(>0.9)", m['score'] > 0.9)


def test_position_tracking() -> None:
    """점을 옮기면 get_character_position 좌표가 따라 바뀌는지 검증."""
    print("\n[2] 캐릭터 위치 추적 (get_character_position)")
    dot = _make_dot_template(8)
    original_capture = screen_capture.capture_region
    try:
        # 위치 A
        screen_capture.capture_region = lambda region: _make_minimap((20, 20), dot=dot)
        pos_a = screen_capture.get_character_position(template=dot, threshold=0.7)
        check("위치 A 인식됨", pos_a is not None)

        # 위치 B (오른쪽 아래로 이동)
        screen_capture.capture_region = lambda region: _make_minimap((100, 80), dot=dot)
        pos_b = screen_capture.get_character_position(template=dot, threshold=0.7)
        check("위치 B 인식됨", pos_b is not None)

        if pos_a and pos_b:
            check("이동 시 좌표 변화", pos_b[0] > pos_a[0] and pos_b[1] > pos_a[1])
            check("위치 A 좌표 정확(≈24,24)",
                  abs(pos_a[0] - 24) <= 2 and abs(pos_a[1] - 24) <= 2)
    finally:
        screen_capture.capture_region = original_capture


def test_no_match() -> None:
    """점이 없거나 매칭 실패 시 None 을 반환하는지 검증."""
    print("\n[3] 매칭 실패 / 점 없음 처리")
    dot = _make_dot_template(8)
    original_capture = screen_capture.capture_region
    try:
        # 점 없는 빈 미니맵 → None
        screen_capture.capture_region = lambda region: _make_minimap(None)
        pos = screen_capture.get_character_position(template=dot, threshold=0.7)
        check("점 없으면 None", pos is None)

        # find_template 직접: 점 없는 이미지 → None
        empty = _make_minimap(None)
        check("빈 미니맵 find_template None",
              screen_capture.find_template(empty, dot, threshold=0.7) is None)

        # 템플릿이 대상보다 크면 None
        big = np.zeros((200, 200, 3), dtype=np.uint8)
        small = _make_minimap((10, 10))
        check("템플릿이 대상보다 크면 None",
              screen_capture.find_template(small, big, threshold=0.7) is None)
    finally:
        screen_capture.capture_region = original_capture


def test_missing_template() -> None:
    """템플릿 파일이 없을 때 안내 후 None 을 반환하는지 검증."""
    print("\n[4] 템플릿 파일 없음 처리")
    # 존재하지 않는 경로 → None (예외 없이)
    t = screen_capture.load_template('assets/minimap/__no_such_dot__.png',
                                     use_cache=False)
    check("없는 템플릿 load → None", t is None)

    # 템플릿 못 읽으면 get_character_position 도 None (캡처 시도 안 함)
    original_load = screen_capture.load_template
    try:
        screen_capture.load_template = lambda path, use_cache=True: None
        pos = screen_capture.get_character_position()
        check("템플릿 없으면 위치 None", pos is None)
    finally:
        screen_capture.load_template = original_load


def run_auto() -> int:
    """헤드리스 자동 검증 실행. 실패 개수를 반환한다."""
    print("===== PHASE 5 미니맵 좌표 인식 테스트 =====")
    if not screen_capture._CV2_AVAILABLE:
        print("  [SKIP] opencv 없음 — 매칭 테스트 불가")
        return 0
    test_find_template()
    test_position_tracking()
    test_no_match()
    test_missing_template()
    print(f"\n===== 결과: {_passed} 통과 / {_failed} 실패 =====")
    print("실게임 보정은 'python test_phase5.py --live' 로 확인하세요.")
    return _failed


def run_live() -> int:
    """실제 게임 미니맵에서 캐릭터 좌표를 1초마다 출력한다 (Ctrl+C 종료)."""
    print("===== PHASE 5 라이브 모드 — 캐릭터 좌표 출력 (Ctrl+C 종료) =====")
    print(f"미니맵 영역: {config.MINIMAP_REGION}")
    print(f"템플릿: {config.MINIMAP_TEMPLATE_PATH}")
    try:
        while True:
            pos = screen_capture.get_character_position(debug=True)
            if pos is None:
                print("  캐릭터 위치: (못 찾음)")
            else:
                print(f"  캐릭터 위치: x={pos[0]} y={pos[1]}")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n종료합니다.")
        return 0


def main() -> None:
    """진입점 — --live 면 라이브, 아니면 자동 검증."""
    if '--live' in sys.argv:
        sys.exit(run_live())
    sys.exit(run_auto())


if __name__ == '__main__':
    main()
