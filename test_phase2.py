"""PHASE 2 라이선스 시스템 테스트 스크립트.

다음을 검증한다.
  1. 하드웨어 ID 생성 (32자리, 동일 기기 반복 일관성)
  2. 로컬 토큰 발급 → 저장 → 검증 라운드트립
  3. 위변조 토큰 / 타 기기 토큰 거부
  4. @require_tier 데코레이터가 등급별로 허용/차단
  5. 등급별 기능 매트릭스 (FREE / BASIC / PREMIUM)

실행:
    python test_phase2.py

주의: 이 스크립트는 license.dat 를 생성/삭제하므로 실제 라이선스 파일이
있다면 백업 후 실행하세요. config.LICENSE_DEV_FORCE_TIER 를 테스트 중
임시로 바꿨다가 끝나면 원복합니다.
"""

import logging
import os

import config
from license import local_validator
from license.hardware_id import get_hardware_id
from license.license_manager import (
    TIER_LEVELS,
    LicenseManager,
    license_manager,
    require_tier,
)

logging.basicConfig(level=logging.WARNING, format='  %(levelname)s: %(message)s')

_passed = 0
_failed = 0


def check(name: str, condition: bool) -> None:
    """단일 검사 결과를 출력하고 전역 카운터를 갱신한다.

    Args:
        name: 검사 이름.
        condition: 통과 여부.
    """
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}")


# ---- @require_tier 검증용 더미 함수들 ----
@require_tier('PREMIUM')
def premium_only_feature() -> str:
    """PREMIUM 전용 더미 기능."""
    return 'yolo_running'


@require_tier('BASIC')
def basic_or_above_feature() -> str:
    """BASIC 이상 더미 기능."""
    return 'basic_running'


def test_hardware_id() -> None:
    """하드웨어 ID 생성 및 일관성 테스트."""
    print("\n[1] 하드웨어 ID")
    hw1 = get_hardware_id()
    hw2 = get_hardware_id()
    print(f"  하드웨어 ID: {hw1}")
    check("32자리 문자열", isinstance(hw1, str) and len(hw1) == 32)
    check("반복 호출 시 동일", hw1 == hw2)


def test_token_roundtrip() -> None:
    """토큰 발급 → 검증 라운드트립 및 위변조/타기기 거부 테스트."""
    print("\n[2] 토큰 발급/검증 라운드트립")
    hw = get_hardware_id()

    token = local_validator.build_token('PREMIUM', hw, license_key='TEST-KEY')
    check("토큰 생성 성공", bool(token))

    payload = local_validator.verify_token(token)
    check("정상 토큰 검증 통과", payload is not None)
    check("등급 일치(PREMIUM)", bool(payload) and payload.get('tier') == 'PREMIUM')

    # 위변조: 토큰 일부를 바꾼 경우
    tampered = ('A' if token[0] != 'A' else 'B') + token[1:]
    check("위변조 토큰 거부", local_validator.verify_token(tampered) is None)

    # 타 기기: 다른 하드웨어ID 로 발급된 토큰
    other = local_validator.build_token('PREMIUM', 'ffffffffffffffffffffffffffffffff')
    check("타 기기 토큰 거부", local_validator.verify_token(other) is None)


def test_save_load() -> None:
    """license.dat 저장/로드 + get_local_tier 테스트."""
    print("\n[3] license.dat 저장/로드")
    backup = None
    path = config.LICENSE_FILE_PATH
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            backup = f.read()
    try:
        hw = get_hardware_id()
        token = local_validator.build_token('BASIC', hw)
        check("저장 성공", local_validator.save_token(token))
        check("로컬 등급 == BASIC", local_validator.get_local_tier() == 'BASIC')
    finally:
        # 원복: 백업이 있으면 복원, 없으면 삭제
        if backup is not None:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(backup)
        elif os.path.exists(path):
            os.remove(path)


def test_require_tier_matrix() -> None:
    """등급별 @require_tier 허용/차단 매트릭스 테스트."""
    print("\n[4] @require_tier 등급별 매트릭스")

    # 전역 싱글톤 대신, 강제 등급을 바꿔가며 검증
    original_forced = config.LICENSE_DEV_FORCE_TIER
    try:
        for tier in ('FREE', 'BASIC', 'PREMIUM'):
            config.LICENSE_DEV_FORCE_TIER = tier
            license_manager.refresh()
            cur = TIER_LEVELS[tier]

            # PREMIUM 기능은 PREMIUM 에서만 통과
            try:
                premium_only_feature()
                premium_ok = True
            except PermissionError:
                premium_ok = False
            check(f"{tier}: PREMIUM기능 {'허용' if cur >= 2 else '차단'}",
                  premium_ok == (cur >= 2))

            # BASIC 기능은 BASIC 이상에서 통과
            try:
                basic_or_above_feature()
                basic_ok = True
            except PermissionError:
                basic_ok = False
            check(f"{tier}: BASIC기능 {'허용' if cur >= 1 else '차단'}",
                  basic_ok == (cur >= 1))

            # is_allowed 직접 확인
            check(f"{tier}: is_allowed(FREE)", license_manager.is_allowed('FREE'))
    finally:
        config.LICENSE_DEV_FORCE_TIER = original_forced
        license_manager.refresh()


def test_activate_flow() -> None:
    """activate(온라인 stub) → 로컬 저장 흐름 테스트."""
    print("\n[5] activate 온라인 stub 흐름")
    backup = None
    path = config.LICENSE_FILE_PATH
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            backup = f.read()

    original_forced = config.LICENSE_DEV_FORCE_TIER
    try:
        # 강제 등급을 끄고 실제 로컬 토큰 경로로 등급이 결정되는지 본다
        config.LICENSE_DEV_FORCE_TIER = None
        mgr = LicenseManager()
        check("활성화 전 FREE", mgr.refresh() == 'FREE')
        check("activate 성공", mgr.activate('DUMMY-LICENSE-KEY'))
        # stub 은 PREMIUM 발급
        check("활성화 후 PREMIUM", mgr.get_tier() == 'PREMIUM')
    finally:
        config.LICENSE_DEV_FORCE_TIER = original_forced
        license_manager.refresh()
        if backup is not None:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(backup)
        elif os.path.exists(path):
            os.remove(path)


def main() -> None:
    """모든 PHASE 2 테스트를 순서대로 실행하고 요약을 출력한다."""
    print("===== PHASE 2 라이선스 시스템 테스트 =====")
    test_hardware_id()
    test_token_roundtrip()
    test_save_load()
    test_require_tier_matrix()
    test_activate_flow()
    print(f"\n===== 결과: {_passed} 통과 / {_failed} 실패 =====")
    raise SystemExit(1 if _failed else 0)


if __name__ == '__main__':
    main()
