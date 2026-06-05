"""매크로 핵심 로직 모듈.

PHASE 3: HP/MP 바를 읽어 임계값 이하면 포션 키를 자동 입력한다.
포션은 쿨다운을 두어 연타를 막고, 모든 키 입력은 input_controller 의
랜덤 딜레이를 거친다. (코드 규칙 2: 고정 딜레이 금지)
"""

import logging
import time

import config
import input_controller
import screen_capture

logger = logging.getLogger(__name__)


class PotionManager:
    """HP/MP 비율을 감시하고 임계값 이하면 포션을 사용하는 관리자.

    포션별 마지막 사용 시각을 기억해 쿨다운 내 재입력을 막는다.
    시간 기준은 monotonic 시계라 시스템 시간 변경에 영향받지 않는다.
    """

    def __init__(self):
        """포션 사용 시각 기록을 초기화한다 (쿨다운 즉시 사용 가능 상태)."""
        # 시작 직후에도 바로 사용할 수 있도록 충분히 과거로 초기화
        self._last_hp_time = 0.0
        self._last_mp_time = 0.0

    def check_and_use_potion(self, debug: bool = False) -> dict:
        """HP/MP 를 1회 확인하고 필요 시 포션 키를 입력한다.

        Args:
            debug: True 면 바 분석 상세를 로그로 출력.

        Returns:
            결과 딕셔너리:
                {'hp': float|None, 'mp': float|None,
                 'hp_used': bool, 'mp_used': bool}
            hp/mp 는 측정된 비율(%), 측정 실패 시 None.
        """
        result = {'hp': None, 'mp': None, 'hp_used': False, 'mp_used': False}
        try:
            now = time.monotonic()

            # ----- HP -----
            hp = screen_capture.get_hp_ratio(debug=debug)
            result['hp'] = hp
            if hp is not None and hp <= config.HP_THRESHOLD_PCT:
                if now - self._last_hp_time >= config.HP_POTION_COOLDOWN:
                    input_controller.press_key(config.HP_POTION_KEY)
                    self._last_hp_time = now
                    result['hp_used'] = True
                    logger.info(
                        f"HP {hp:.0f}% ≤ {config.HP_THRESHOLD_PCT}% → "
                        f"HP 포션('{config.HP_POTION_KEY}') 사용"
                    )
                else:
                    logger.debug(f"HP 낮음({hp:.0f}%) 이나 쿨다운 중")

            # ----- MP -----
            mp = screen_capture.get_mp_ratio(debug=debug)
            result['mp'] = mp
            if mp is not None and mp <= config.MP_THRESHOLD_PCT:
                if now - self._last_mp_time >= config.MP_POTION_COOLDOWN:
                    input_controller.press_key(config.MP_POTION_KEY)
                    self._last_mp_time = now
                    result['mp_used'] = True
                    logger.info(
                        f"MP {mp:.0f}% ≤ {config.MP_THRESHOLD_PCT}% → "
                        f"MP 포션('{config.MP_POTION_KEY}') 사용"
                    )
                else:
                    logger.debug(f"MP 낮음({mp:.0f}%) 이나 쿨다운 중")

            return result
        except Exception as e:
            logger.error(f"포션 체크 실패: {e}")
            return result


# 프로그램 전역에서 공유하는 싱글톤 — main 루프에서 매 틱 호출한다
potion_manager = PotionManager()


def check_and_use_potion(debug: bool = False) -> dict:
    """전역 potion_manager.check_and_use_potion 의 단축 래퍼.

    Args:
        debug: True 면 바 분석 상세를 로그로 출력.

    Returns:
        check_and_use_potion 결과 딕셔너리.
    """
    return potion_manager.check_and_use_potion(debug=debug)
