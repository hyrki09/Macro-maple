"""라이선스 검증 총괄 모듈.

프로그램 전체에서 등급을 조회하고 기능 접근을 통제하는 단일 진입점.
다른 모듈은 이 파일의 `license_manager` 싱글톤과 `@require_tier` 데코레이터만
사용하면 된다. (내부의 hardware_id / local / online 모듈을 직접 다루지 않는다.)

등급 결정 우선순위:
    1) config.LICENSE_DEV_FORCE_TIER 가 설정돼 있으면 그 등급으로 강제 (개발용)
    2) 로컬 license.dat 토큰이 유효하면 그 등급
    3) 둘 다 아니면 FREE
"""

import logging
from functools import wraps

import config
from license import local_validator
from license.online_validator import verify_online

logger = logging.getLogger(__name__)

# 등급 서열 — 숫자가 클수록 상위 등급
TIER_LEVELS = {'FREE': 0, 'BASIC': 1, 'PREMIUM': 2}


class LicenseManager:
    """라이선스 등급 조회와 활성화를 담당하는 클래스."""

    def __init__(self):
        """매니저 초기화 — 등급 캐시를 비워둔다."""
        self._cached_tier: str | None = None

    def get_tier(self) -> str:
        """현재 라이선스 등급을 반환한다 — FREE / BASIC / PREMIUM.

        결정 우선순위는 모듈 docstring 참고. 결과는 캐시되며,
        활성화(activate)나 refresh() 호출 시 갱신된다.

        Returns:
            현재 등급 문자열. 어떤 경로로도 확정 못 하면 'FREE'.
        """
        try:
            if self._cached_tier is not None:
                return self._cached_tier

            # 1) 개발용 강제 등급
            forced = getattr(config, 'LICENSE_DEV_FORCE_TIER', None)
            if forced in TIER_LEVELS:
                logger.warning(
                    f"개발용 강제 등급 적용: {forced} "
                    "(배포 시 config.LICENSE_DEV_FORCE_TIER 를 None 으로)"
                )
                self._cached_tier = forced
                return forced

            # 2) 로컬 토큰 검증
            local_tier = local_validator.get_local_tier()
            if local_tier in TIER_LEVELS:
                self._cached_tier = local_tier
                return local_tier

            # 3) 미인증 → FREE
            self._cached_tier = 'FREE'
            return 'FREE'
        except Exception as e:
            logger.error(f"등급 조회 실패 — FREE 로 폴백: {e}")
            return 'FREE'

    def refresh(self) -> str:
        """등급 캐시를 비우고 다시 조회한다.

        Returns:
            새로 조회한 등급 문자열.
        """
        self._cached_tier = None
        return self.get_tier()

    def is_allowed(self, required_tier: str) -> bool:
        """현재 등급이 required_tier 이상인지 확인한다.

        Args:
            required_tier: 요구 등급 (FREE / BASIC / PREMIUM).

        Returns:
            현재 등급이 요구 등급 이상이면 True.
        """
        try:
            current = TIER_LEVELS.get(self.get_tier(), 0)
            required = TIER_LEVELS.get(required_tier, 999)
            return current >= required
        except Exception as e:
            logger.error(f"등급 비교 실패: {e}")
            return False

    def activate(self, license_key: str) -> bool:
        """라이선스 키로 온라인 인증 후 로컬에 토큰을 저장한다 (최초 1회).

        성공하면 등급 캐시를 갱신해 즉시 반영한다.

        Args:
            license_key: 사용자가 입력한 라이선스 키.

        Returns:
            활성화 성공 여부.
        """
        try:
            result = verify_online(license_key)
            if not result.get('ok'):
                logger.error(f"라이선스 활성화 실패: {result.get('error')}")
                return False

            if not local_validator.save_token(result['token']):
                logger.error("토큰 저장 실패로 활성화 중단.")
                return False

            self.refresh()
            logger.info(f"라이선스 활성화 완료 — 등급: {self.get_tier()}")
            return True
        except Exception as e:
            logger.error(f"라이선스 활성화 중 오류: {e}")
            return False


def require_tier(tier: str):
    """라이선스 등급 체크 데코레이터.

    감싼 함수 실행 전에 현재 등급이 `tier` 이상인지 확인하고,
    부족하면 PermissionError 를 발생시킨다.

    Args:
        tier: 요구 등급 (FREE / BASIC / PREMIUM).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not license_manager.is_allowed(tier):
                raise PermissionError(
                    f"이 기능은 {tier} 등급 이상에서만 사용 가능합니다. "
                    f"(현재 등급: {license_manager.get_tier()})"
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


# 프로그램 전역에서 공유하는 싱글톤 인스턴스
license_manager = LicenseManager()
