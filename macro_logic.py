"""매크로 핵심 로직 모듈.

PHASE 3: HP/MP 바를 읽어 임계값 이하면 포션 키를 자동 입력한다.
PHASE 4: 설정한 순서대로 스킬 키를 입력하는 스킬 콤보 자동화.
         고스펙(모드1) 콤보는 PREMIUM 등급에서만 사용 가능하다.
포션/콤보 모두 쿨다운 또는 랜덤 지터를 적용하고, 모든 키 입력은
input_controller 의 랜덤 딜레이를 거친다. (코드 규칙 2: 고정 딜레이 금지)
"""

import logging
import random
import time

import config
import input_controller
import screen_capture
from license.license_manager import require_tier

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


def _jittered_delay(base: float) -> float:
    """콤보 기본 딜레이에 랜덤 지터(±SKILL_DELAY_JITTER)를 적용한 값을 반환한다.

    고정 패턴을 피하기 위함이다. (코드 규칙 2: 고정 딜레이 금지)
    base 가 0 이하면 지터 없이 0 을 돌려준다(딜레이 없음).

    Args:
        base: 콤보에 정의된 기본 딜레이(초).

    Returns:
        지터가 적용된 딜레이(초). 음수가 되지 않도록 0 으로 하한 처리.
    """
    if base <= 0:
        return 0.0
    jitter = config.SKILL_DELAY_JITTER
    return max(0.0, random.uniform(base * (1 - jitter), base * (1 + jitter)))


class SkillComboManager:
    """설정된 스킬 콤보를 순서대로 입력하는 관리자.

    콤보는 [(키, 기본딜레이(초)), ...] 형태이며, 각 키를 누른 뒤
    기본딜레이에 랜덤 지터를 적용해 대기한다.
    고스펙(모드1) 콤보는 @require_tier 로 PREMIUM 등급에서만 실행된다.
    """

    def _run_combo(self, combo: list, mode: str) -> dict:
        """콤보 한 벌을 실제로 입력한다 (등급 체크 없는 내부 실행).

        Args:
            combo: [(키, 기본딜레이(초)), ...] 콤보 정의.
            mode: 로그/결과에 표시할 모드 식별자.

        Returns:
            결과 딕셔너리:
                {'mode': str, 'ok': bool, 'denied': bool, 'keys': list[str]}
            keys 는 실제로 입력된 키 순서.
        """
        result = {'mode': mode, 'ok': False, 'denied': False, 'keys': []}
        try:
            if not combo:
                logger.warning(f"스킬 콤보가 비어 있음 (모드: {mode})")
                result['ok'] = True   # 입력할 게 없을 뿐 오류는 아님
                return result

            for key, base_delay in combo:
                input_controller.press_key(key)
                result['keys'].append(key)
                delay = _jittered_delay(base_delay)
                if delay > 0:
                    time.sleep(delay)

            result['ok'] = True
            logger.info(
                f"스킬 콤보 실행 완료 (모드: {mode}) → {''.join(result['keys'])}"
            )
            return result
        except Exception as e:
            logger.error(f"스킬 콤보 실행 실패 (모드: {mode}): {e}")
            return result

    @require_tier('PREMIUM')
    def execute_combo_highspec(self) -> dict:
        """고스펙(모드1) 콤보를 실행한다 — PREMIUM 등급 전용.

        등급이 부족하면 @require_tier 가 PermissionError 를 발생시킨다.

        Returns:
            _run_combo 결과 딕셔너리.
        """
        return self._run_combo(config.SKILL_COMBO_MODE1, config.SKILL_MODE_HIGHSPEC)

    def execute_combo_lowspec(self) -> dict:
        """저스펙(모드2) 콤보를 실행한다 — 전 등급 사용 가능.

        Returns:
            _run_combo 결과 딕셔너리.
        """
        return self._run_combo(config.SKILL_COMBO_MODE2, config.SKILL_MODE_LOWSPEC)

    def execute_skill_combo(self, mode: str | None = None) -> dict:
        """지정한 모드의 스킬 콤보를 1회 실행한다.

        고스펙 모드는 PREMIUM 등급에서만 동작하며, 등급이 부족하면
        예외를 밖으로 던지지 않고 결과 딕셔너리에 denied=True 로 알린다.
        (메인 루프가 멈추지 않도록 안전하게 처리)

        Args:
            mode: 'highspec' / 'lowspec'. None 이면 config.SKILL_MODE_DEFAULT.

        Returns:
            결과 딕셔너리:
                {'mode': str, 'ok': bool, 'denied': bool, 'keys': list[str]}
        """
        if mode is None:
            mode = config.SKILL_MODE_DEFAULT
        try:
            if mode == config.SKILL_MODE_HIGHSPEC:
                return self.execute_combo_highspec()
            if mode == config.SKILL_MODE_LOWSPEC:
                return self.execute_combo_lowspec()
            logger.error(f"알 수 없는 스킬 모드: {mode}")
            return {'mode': mode, 'ok': False, 'denied': False, 'keys': []}
        except PermissionError as e:
            logger.warning(f"스킬 콤보 권한 거부 (모드: {mode}): {e}")
            return {'mode': mode, 'ok': False, 'denied': True, 'keys': []}
        except Exception as e:
            logger.error(f"스킬 콤보 디스패치 실패 (모드: {mode}): {e}")
            return {'mode': mode, 'ok': False, 'denied': False, 'keys': []}


# 프로그램 전역에서 공유하는 싱글톤 — 사냥 루프에서 호출한다
skill_combo_manager = SkillComboManager()


def execute_skill_combo(mode: str | None = None) -> dict:
    """전역 skill_combo_manager.execute_skill_combo 의 단축 래퍼.

    Args:
        mode: 'highspec' / 'lowspec'. None 이면 기본 모드.

    Returns:
        execute_skill_combo 결과 딕셔너리.
    """
    return skill_combo_manager.execute_skill_combo(mode=mode)
