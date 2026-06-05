"""하드웨어 고유 ID 생성 모듈.

CPU ProcessorId 와 MAC 주소를 조합해 기기마다 다른 고유 식별자를 만든다.
이 ID 는 라이선스 토큰에 바인딩되어, 한 라이선스가 다른 PC 로 복사되어도
검증에 실패하도록 만든다. (코드 규칙 5: 메모리 직접 읽기 사용 안 함)
"""

import hashlib
import logging
import subprocess
import uuid

logger = logging.getLogger(__name__)

# 동일 실행 중 반복 호출 시 wmic 재실행을 막기 위한 캐시
_cached_hardware_id: str | None = None


def _get_mac() -> str:
    """현재 기기의 MAC 주소를 16진수 문자열로 반환한다.

    Returns:
        uuid.getnode() 기반 MAC 16진수 문자열. 실패 시 빈 문자열.
    """
    try:
        return hex(uuid.getnode())
    except Exception as e:
        logger.error(f"MAC 주소 조회 실패: {e}")
        return ""


def _get_cpu_id() -> str:
    """Windows wmic 으로 CPU ProcessorId 를 조회한다.

    Returns:
        CPU ProcessorId 문자열. 조회 실패 시 빈 문자열.
    """
    try:
        output = subprocess.check_output(
            'wmic cpu get ProcessorId',
            shell=True,
            stderr=subprocess.DEVNULL,
        ).decode(errors='ignore').strip()
        # 출력 예: "ProcessorId\nBFEBFBFF000406E3" → 마지막 토큰이 ID
        tokens = output.split()
        if len(tokens) >= 2:
            return tokens[-1]
        logger.warning(f"CPU ID 파싱 결과가 비어있음: {output!r}")
        return ""
    except Exception as e:
        logger.error(f"CPU ID 조회 실패 (wmic): {e}")
        return ""


def get_hardware_id() -> str:
    """CPU ID + MAC 주소를 조합해 고유한 하드웨어 ID 를 생성한다.

    CPU 조회에 실패해도 MAC 만으로 ID 를 만들어 프로그램이 동작하도록 한다.
    결과는 SHA-256 해시의 앞 32자리(16진수) 문자열이다.

    Returns:
        32자리 16진수 하드웨어 ID 문자열.
    """
    global _cached_hardware_id
    try:
        if _cached_hardware_id is not None:
            return _cached_hardware_id

        mac = _get_mac()
        cpu = _get_cpu_id()

        if cpu:
            raw = f"{mac}-{cpu}"
        else:
            # CPU 조회 실패 시 MAC 단독 폴백 (CLAUDE.md 패턴)
            logger.warning("CPU ID 조회 실패 — MAC 주소만으로 하드웨어 ID 생성")
            raw = mac

        if not raw:
            # MAC 마저 실패한 극단적 상황 — 고정 폴백으로라도 ID 발급
            logger.error("MAC/CPU 모두 조회 실패 — 폴백 하드웨어 ID 사용")
            raw = "unknown-hardware"

        _cached_hardware_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
        return _cached_hardware_id
    except Exception as e:
        logger.error(f"하드웨어 ID 생성 실패: {e}")
        # 최후의 폴백 — 빈 문자열 대신 결정적 더미 해시 반환
        return hashlib.sha256(b"fallback").hexdigest()[:32]


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print(f"하드웨어 ID: {get_hardware_id()}")
