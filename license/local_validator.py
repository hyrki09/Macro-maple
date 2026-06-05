"""로컬 라이선스 토큰 검증 모듈.

최초 온라인 인증으로 받은 서명 토큰을 license.dat 에 저장하고,
이후 실행부터는 인터넷 없이 이 파일만으로 등급을 검증한다.

토큰 구조 (서명 후 base64 인코딩):
    {
        "payload":   {"tier", "hardware_id", "license_key", "issued_at"},
        "signature": HMAC-SHA256(payload, LICENSE_SIGNING_SECRET)
    }

검증 시 두 가지를 확인한다.
    1) 서명이 일치하는가 (토큰 위변조 방지)
    2) payload 의 hardware_id 가 현재 기기와 같은가 (타 PC 복사 방지)
"""

import base64
import hashlib
import hmac
import json
import logging
import time

import config
from license.hardware_id import get_hardware_id

logger = logging.getLogger(__name__)

VALID_TIERS = ('FREE', 'BASIC', 'PREMIUM')


def _canonical(payload: dict) -> bytes:
    """payload 를 서명용 정규화 바이트로 직렬화한다.

    키 정렬과 공백 제거로 항상 동일한 바이트열이 나오게 하여
    서명/검증 결과가 일관되도록 한다.

    Args:
        payload: 서명 대상 딕셔너리.

    Returns:
        정규화된 UTF-8 바이트열.
    """
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')


def sign_payload(payload: dict) -> str:
    """payload 에 대한 HMAC-SHA256 서명을 16진수 문자열로 반환한다.

    Args:
        payload: 서명할 딕셔너리.

    Returns:
        16진수 서명 문자열. 실패 시 빈 문자열.
    """
    try:
        secret = config.LICENSE_SIGNING_SECRET.encode('utf-8')
        return hmac.new(secret, _canonical(payload), hashlib.sha256).hexdigest()
    except Exception as e:
        logger.error(f"서명 생성 실패: {e}")
        return ""


def build_token(tier: str, hardware_id: str, license_key: str = "") -> str:
    """등급/하드웨어ID 로 서명된 라이선스 토큰 문자열을 만든다.

    실제 환경에서는 서버가 이 작업을 수행하지만, PHASE 2 stub 에서는
    online_validator 가 이 함수를 재사용해 토큰을 발급한다.

    Args:
        tier: 라이선스 등급 (FREE / BASIC / PREMIUM).
        hardware_id: 토큰을 바인딩할 하드웨어 ID.
        license_key: 발급에 사용된 라이선스 키 (기록용, 선택).

    Returns:
        base64 인코딩된 토큰 문자열. 실패 시 빈 문자열.
    """
    try:
        if tier not in VALID_TIERS:
            logger.error(f"알 수 없는 등급으로 토큰 생성 시도: {tier}")
            return ""
        payload = {
            'tier': tier,
            'hardware_id': hardware_id,
            'license_key': license_key,
            'issued_at': int(time.time()),
        }
        token_obj = {'payload': payload, 'signature': sign_payload(payload)}
        raw = json.dumps(token_obj).encode('utf-8')
        return base64.b64encode(raw).decode('ascii')
    except Exception as e:
        logger.error(f"토큰 생성 실패: {e}")
        return ""


def save_token(token: str) -> bool:
    """토큰 문자열을 license.dat 에 저장한다.

    Args:
        token: build_token 으로 만든 base64 토큰 문자열.

    Returns:
        저장 성공 여부.
    """
    try:
        if not token:
            logger.error("빈 토큰은 저장할 수 없습니다.")
            return False
        with open(config.LICENSE_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(token)
        logger.info(f"라이선스 토큰 저장 완료: {config.LICENSE_FILE_PATH}")
        return True
    except Exception as e:
        logger.error(f"라이선스 토큰 저장 실패: {e}")
        return False


def load_token() -> str | None:
    """license.dat 에서 토큰 문자열을 읽어온다.

    Returns:
        토큰 문자열. 파일이 없거나 읽기 실패 시 None.
    """
    try:
        with open(config.LICENSE_FILE_PATH, 'r', encoding='utf-8') as f:
            token = f.read().strip()
        return token or None
    except FileNotFoundError:
        logger.info("라이선스 파일이 없습니다 (미인증 상태).")
        return None
    except Exception as e:
        logger.error(f"라이선스 토큰 읽기 실패: {e}")
        return None


def verify_token(token: str | None = None) -> dict | None:
    """토큰의 서명과 하드웨어ID 바인딩을 검증한다.

    Args:
        token: 검증할 토큰 문자열. None 이면 license.dat 에서 로드한다.

    Returns:
        검증에 성공하면 payload 딕셔너리, 실패하면 None.
    """
    try:
        if token is None:
            token = load_token()
        if not token:
            return None

        raw = base64.b64decode(token.encode('ascii'))
        token_obj = json.loads(raw.decode('utf-8'))
        payload = token_obj.get('payload')
        signature = token_obj.get('signature')

        if not isinstance(payload, dict) or not signature:
            logger.warning("토큰 구조가 올바르지 않습니다.")
            return None

        # 1) 서명 검증 — 타이밍 공격 방지를 위해 compare_digest 사용
        expected = sign_payload(payload)
        if not expected or not hmac.compare_digest(expected, signature):
            logger.warning("라이선스 서명 검증 실패 — 위변조 가능성.")
            return None

        # 2) 하드웨어ID 바인딩 검증
        current_hw = get_hardware_id()
        if payload.get('hardware_id') != current_hw:
            logger.warning("라이선스가 다른 기기에 발급됨 — 하드웨어ID 불일치.")
            return None

        # 3) 등급 유효성
        if payload.get('tier') not in VALID_TIERS:
            logger.warning(f"토큰의 등급이 유효하지 않음: {payload.get('tier')}")
            return None

        return payload
    except Exception as e:
        logger.error(f"라이선스 토큰 검증 실패: {e}")
        return None


def get_local_tier() -> str | None:
    """로컬 토큰을 검증해 유효한 등급을 반환한다.

    Returns:
        검증 성공 시 등급 문자열, 실패/미인증 시 None.
    """
    payload = verify_token()
    return payload.get('tier') if payload else None
