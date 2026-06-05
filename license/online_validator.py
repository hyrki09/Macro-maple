"""온라인 라이선스 서버 검증 모듈.

최초 1회, 사용자가 입력한 라이선스 키와 하드웨어 ID 를 서버로 보내
등급을 확인받고 서명된 토큰을 발급받는다.

PHASE 2 현재는 실제 서버가 없으므로 stub 으로 동작한다.
  - 항상 PREMIUM 등급 토큰을 발급한다 (전체 기능 개발/테스트 목적).
  - 실제 서버 연동은 verify_online() 안의 TODO 부분에서 진행한다.
"""

import logging

import config
from license import local_validator
from license.hardware_id import get_hardware_id

logger = logging.getLogger(__name__)

# PHASE 2 stub 이 발급하는 등급. 실제 서버 연동 시 서버 응답으로 대체된다.
_STUB_TIER = 'PREMIUM'


def verify_online(license_key: str) -> dict:
    """라이선스 키를 온라인 서버에 검증 요청하고 결과를 반환한다.

    PHASE 2 stub: 네트워크 호출 없이 항상 PREMIUM 토큰을 발급한다.

    Args:
        license_key: 사용자가 입력한 라이선스 키.

    Returns:
        결과 딕셔너리.
            성공: {'ok': True,  'tier': <등급>, 'token': <서명토큰>}
            실패: {'ok': False, 'tier': None,   'error': <사유>}
    """
    try:
        hardware_id = get_hardware_id()

        # ===== TODO(실서버 연동): 아래 stub 을 실제 HTTP 요청으로 교체 =====
        # import requests
        # resp = requests.post(
        #     config.LICENSE_SERVER_URL,
        #     json={'license_key': license_key, 'hardware_id': hardware_id},
        #     timeout=config.LICENSE_SERVER_TIMEOUT,
        # )
        # resp.raise_for_status()
        # data = resp.json()           # 서버가 {'tier':..., 'token':...} 반환
        # tier  = data['tier']
        # token = data['token']        # 서버가 비밀키로 서명한 토큰
        # =================================================================

        # --- PHASE 2 stub 시작 ---
        logger.info(
            "온라인 검증 stub 동작 — 항상 PREMIUM 발급 "
            "(실서버 연동 전 개발용)"
        )
        tier = _STUB_TIER
        # 서버가 했어야 할 서명을 로컬에서 대신 생성 (개발용)
        token = local_validator.build_token(
            tier=tier,
            hardware_id=hardware_id,
            license_key=license_key,
        )
        # --- PHASE 2 stub 끝 ---

        if not token:
            return {'ok': False, 'tier': None, 'error': '토큰 발급 실패'}

        logger.info(f"온라인 검증 성공 — 등급: {tier}")
        return {'ok': True, 'tier': tier, 'token': token}
    except Exception as e:
        logger.error(f"온라인 라이선스 검증 실패: {e}")
        return {'ok': False, 'tier': None, 'error': str(e)}
