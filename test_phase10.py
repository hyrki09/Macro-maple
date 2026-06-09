"""PHASE 10 설정 UI 테스트 스크립트.

실제 창을 띄우지 않고(Tk 비의존 순수 로직 + 파일 입출력) 헤드리스로 검증한다.

  python test_phase10.py

검증 항목
  1) user_config 라운드트립 — 저장 후 로드 시 값 유지(재실행해도 유지)
  2) 기본값/병합        — 파일 없음/부분 설정 시 기본값 채움, 미지 키 보존
  3) 등급 게이팅        — allowed_* 가 등급별 허용 항목만 반환
  4) enforce 강등       — 하위 등급이 상위 전용 선택 시 안전 강등
  5) build_config       — UI 값 → 저장 설정 구성(숫자 변환/블록 반영/강등)
  6) to_int             — 안전한 정수 변환
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
import settings_ui
import user_config

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


def test_roundtrip() -> None:
    """저장 후 로드 시 값이 유지되는지(재실행 시나리오) 검증."""
    print("\n[1] user_config 저장/로드 라운드트립")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'config.json')
        cfg = user_config.default_config()
        cfg['hunt_mode'] = config.HUNT_MODE_YOLO
        cfg['map'] = config.MAP_RED_ELEPHANT2_MINI
        cfg['skill_mode'] = config.SKILL_MODE_HIGHSPEC
        cfg['telegram']['token'] = 'TK123'
        cfg['telegram']['chat_id'] = '999'
        cfg['shop']['buy_quantity'] = 42

        check("저장 성공", user_config.save_config(cfg, p) is True)
        check("파일 생성됨", os.path.exists(p))

        loaded = user_config.load_config(p)
        check("사냥 방식 유지", loaded['hunt_mode'] == config.HUNT_MODE_YOLO)
        check("맵 유지", loaded['map'] == config.MAP_RED_ELEPHANT2_MINI)
        check("스킬 모드 유지", loaded['skill_mode'] == config.SKILL_MODE_HIGHSPEC)
        check("텔레그램 토큰 유지", loaded['telegram']['token'] == 'TK123')
        check("구매 수량 유지", loaded['shop']['buy_quantity'] == 42)

        # 한글이 깨지지 않게 저장되는지(ensure_ascii=False) — 파일 직접 확인
        cfg['license_key'] = '키-한글'
        user_config.save_config(cfg, p)
        with open(p, 'r', encoding='utf-8') as f:
            raw = f.read()
        check("한글 그대로 저장", '키-한글' in raw)


def test_defaults_merge() -> None:
    """파일 없음/부분 설정 시 기본값 채움 + 미지 키 보존 검증."""
    print("\n[2] 기본값/병합")
    # (a) 파일 없음 → 전체 기본값
    cfg = user_config.load_config('___none___.json')
    check("파일 없으면 기본값", cfg['hunt_mode'] == config.HUNT_MODE_DEFAULT
          and cfg['telegram']['enabled'] is False
          and cfg['shop']['buy_quantity'] == config.SHOP_DEFAULTS['buy_quantity'])

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'config.json')
        # (b) 부분 설정 + 미지 키 → 나머지는 기본값, 미지 키 보존, 블록 부분병합
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'map': config.MAP_RED_ELEPHANT2_MINI,
                       'telegram': {'token': 'X'},
                       'future_key': 123}, f)
        cfg = user_config.load_config(p)
        check("지정 값 반영", cfg['map'] == config.MAP_RED_ELEPHANT2_MINI)
        check("미지정은 기본값", cfg['skill_mode'] == config.SKILL_MODE_DEFAULT)
        check("블록 부분 병합(token 반영, enabled 기본)",
              cfg['telegram']['token'] == 'X' and cfg['telegram']['enabled'] is False)
        check("미지 키 보존", cfg.get('future_key') == 123)

        # (c) 손상 JSON → 기본값
        with open(p, 'w', encoding='utf-8') as f:
            f.write('{ broken')
        cfg = user_config.load_config(p)
        check("손상 JSON 이면 기본값", cfg['hunt_mode'] == config.HUNT_MODE_DEFAULT)


def test_tier_gating() -> None:
    """allowed_* 가 등급별 허용 항목만 반환하는지 검증."""
    print("\n[3] 등급 게이팅")
    # 사냥 방식 — YOLO 는 PREMIUM
    check("FREE 사냥: 패턴만",
          settings_ui.allowed_hunt_modes('FREE') == [config.HUNT_MODE_PATTERN])
    check("PREMIUM 사냥: YOLO 포함",
          config.HUNT_MODE_YOLO in settings_ui.allowed_hunt_modes('PREMIUM'))

    # 맵 — FREE 1개 고정, BASIC+ 전체
    check("FREE 맵: 1개 고정",
          settings_ui.allowed_maps('FREE') == [config.MAP_DEFAULT])
    check("BASIC 맵: 전체",
          len(settings_ui.allowed_maps('BASIC')) == 2)
    check("PREMIUM 맵: 전체",
          config.MAP_RED_ELEPHANT2_MINI in settings_ui.allowed_maps('PREMIUM'))

    # 모드 — 고스펙은 PREMIUM
    check("FREE 모드: 저스펙만",
          settings_ui.allowed_skill_modes('FREE') == [config.SKILL_MODE_LOWSPEC])
    check("BASIC 모드: 저스펙만(고스펙 불가)",
          config.SKILL_MODE_HIGHSPEC not in settings_ui.allowed_skill_modes('BASIC'))
    check("PREMIUM 모드: 고스펙 포함",
          config.SKILL_MODE_HIGHSPEC in settings_ui.allowed_skill_modes('PREMIUM'))


def test_enforce() -> None:
    """enforce_tier_permissions 강등 검증."""
    print("\n[4] enforce 강등")
    over = {'hunt_mode': config.HUNT_MODE_YOLO,
            'map': config.MAP_RED_ELEPHANT2_MINI,
            'skill_mode': config.SKILL_MODE_HIGHSPEC}

    # FREE: 모두 강등
    free = settings_ui.enforce_tier_permissions(over, 'FREE')
    check("FREE 사냥 강등", free['hunt_mode'] == config.HUNT_MODE_DEFAULT)
    check("FREE 맵 강등", free['map'] == config.MAP_DEFAULT)
    check("FREE 모드 강등", free['skill_mode'] == config.SKILL_MODE_LOWSPEC)

    # BASIC: 맵은 허용, 사냥/모드는 강등
    basic = settings_ui.enforce_tier_permissions(over, 'BASIC')
    check("BASIC 맵 유지", basic['map'] == config.MAP_RED_ELEPHANT2_MINI)
    check("BASIC 사냥 강등", basic['hunt_mode'] == config.HUNT_MODE_DEFAULT)
    check("BASIC 모드 강등", basic['skill_mode'] == config.SKILL_MODE_LOWSPEC)

    # PREMIUM: 모두 유지
    prem = settings_ui.enforce_tier_permissions(over, 'PREMIUM')
    check("PREMIUM 전부 유지",
          prem['hunt_mode'] == config.HUNT_MODE_YOLO
          and prem['map'] == config.MAP_RED_ELEPHANT2_MINI
          and prem['skill_mode'] == config.SKILL_MODE_HIGHSPEC)

    # 원본 불변
    check("원본 딕셔너리 불변", over['hunt_mode'] == config.HUNT_MODE_YOLO)


def test_build_config() -> None:
    """build_config 가 UI 값을 저장 설정으로 구성하는지 검증."""
    print("\n[5] build_config")
    base = user_config.default_config()
    values = {
        'license_key': 'LK',
        'hunt_mode': config.HUNT_MODE_YOLO,
        'map': config.MAP_RED_ELEPHANT2_MINI,
        'skill_mode': config.SKILL_MODE_HIGHSPEC,
        'buy_quantity': '50',          # 문자열 → int
        'shop_interval': '900',
        'pet_feed_interval': '120',
        'teleport_interval': 'bad',    # 잘못된 값 → 기본값
        'telegram_enabled': True,
        'telegram_token': 'TT',
        'telegram_chat_id': 'CC',
        'shop_enabled': False,
    }

    # PREMIUM: 모든 선택 유지 + 숫자 변환
    cfg = settings_ui.build_config(values, base, 'PREMIUM')
    check("license_key 반영", cfg['license_key'] == 'LK')
    check("hunt_mode 반영(PREMIUM)", cfg['hunt_mode'] == config.HUNT_MODE_YOLO)
    check("buy_quantity 문자열→int", cfg['shop']['buy_quantity'] == 50)
    check("shop_interval 반영", cfg['shop']['interval_sec'] == 900)
    check("잘못된 텔레포트→기본값",
          cfg['teleport_interval'] == config.USER_CONFIG_DEFAULTS['teleport_interval'])
    check("telegram 블록 반영",
          cfg['telegram']['enabled'] is True and cfg['telegram']['token'] == 'TT')
    check("shop_enabled 반영", cfg['shop']['enabled'] is False)

    # FREE: 상위 선택 강등
    cfg_free = settings_ui.build_config(values, base, 'FREE')
    check("FREE 빌드 시 사냥 강등", cfg_free['hunt_mode'] == config.HUNT_MODE_DEFAULT)
    check("FREE 빌드 시 맵 강등", cfg_free['map'] == config.MAP_DEFAULT)
    check("FREE 빌드 시 모드 강등", cfg_free['skill_mode'] == config.SKILL_MODE_LOWSPEC)


def test_to_int() -> None:
    """to_int 안전 변환 검증."""
    print("\n[6] to_int")
    check("정수 문자열", settings_ui.to_int('30', 0) == 30)
    check("실수 문자열→내림", settings_ui.to_int('12.9', 0) == 12)
    check("음수→0 하한", settings_ui.to_int('-5', 0) == 0)
    check("빈값→기본값", settings_ui.to_int('', 7) == 7)
    check("None→기본값", settings_ui.to_int(None, 7) == 7)
    check("문자→기본값", settings_ui.to_int('abc', 7) == 7)


def main() -> None:
    """헤드리스 자동 검증 실행."""
    print("===== PHASE 10 설정 UI 테스트 =====")
    test_roundtrip()
    test_defaults_merge()
    test_tier_gating()
    test_enforce()
    test_build_config()
    test_to_int()
    print(f"\n===== 결과: {_passed} 통과 / {_failed} 실패 =====")
    sys.exit(_failed)


if __name__ == '__main__':
    main()
