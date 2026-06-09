"""매매 루틴 모듈 (PHASE 9) [PREMIUM].

설정 주기마다 상점으로 이동 → 아이템 판매 → 소모품 구매 → 사냥터 복귀를
자동으로 수행한다. 전체 흐름과 각 단계는 PREMIUM 등급에서만 동작한다.

  - go_to_shop()        : 상점/NPC 로 이동해 상점 창을 연다
  - sell_items()        : 판매 탭에서 아이템을 일괄 판매한다
  - buy_consumables()   : 구매 탭에서 소모품을 설정 수량만큼 구매한다
  - return_to_hunting() : 상점을 닫고 사냥터로 복귀한다
  - run_routine()       : 위 네 단계를 순서대로 실행하는 오케스트레이터

실제 게임의 NPC/메뉴 조작 키는 게임마다 달라 config 의 키 시퀀스로 빼두었고
사용자가 보정한다. 모든 딜레이는 random.uniform (코드 규칙 2), 모든 키 입력은
input_controller 의 랜덤 딜레이를 거친다. 등급 부족 시 @require_tier 가
PermissionError 를 던지며, run_routine 은 이를 denied=True 로 안전 처리해
메인 루프를 멈추지 않는다.

(코드 규칙 1: 한국어 docstring, 3: 설정은 config 에서, 6: 예외처리 필수,
 7: logging 사용, 8: PREMIUM 전용은 라이선스 체크 후 실행)
"""

import json
import logging
import os
import random
import time

import config
import input_controller
from license.license_manager import require_tier

logger = logging.getLogger(__name__)


def _jittered(base: float) -> float:
    """단계 키 기본딜레이에 랜덤 지터(±SHOP_DELAY_JITTER)를 적용해 반환한다.

    base 가 0 이하면 지터 없이 0 을 돌려준다(딜레이 없음).

    Args:
        base: 시퀀스에 정의된 기본 딜레이(초).

    Returns:
        지터가 적용된 딜레이(초). 음수가 되지 않도록 0 으로 하한 처리.
    """
    if base <= 0:
        return 0.0
    j = config.SHOP_DELAY_JITTER
    return max(0.0, random.uniform(base * (1 - j), base * (1 + j)))


def load_shop_config(path: str | None = None) -> dict:
    """config.json 에서 매매(shop) 설정 블록을 읽어 반환한다.

    파일이 없거나 shop 블록이 없으면 SHOP_DEFAULTS 로 채운다.
    interval_sec / buy_quantity 는 숫자로 안전하게 변환한다.

    Args:
        path: config.json 경로. None 이면 config.CONFIG_JSON_PATH.

    Returns:
        {'enabled', 'interval_sec', 'buy_quantity'} 키를 가진 설정 딕셔너리.
    """
    cfg = dict(config.SHOP_DEFAULTS)
    try:
        if path is None:
            path = config.CONFIG_JSON_PATH
        if not os.path.exists(path):
            logger.debug(f"config.json 없음 — 매매 기본값 사용: {path}")
            return cfg
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        block = data.get(config.SHOP_CONFIG_KEY, {})
        if isinstance(block, dict):
            cfg.update({k: block[k] for k in cfg if k in block})
        # 숫자 필드 안전 변환
        cfg['enabled'] = bool(cfg.get('enabled', True))
        cfg['interval_sec'] = float(cfg.get('interval_sec', config.SHOP_INTERVAL))
        cfg['buy_quantity'] = max(0, int(cfg.get('buy_quantity', 0)))
        return cfg
    except Exception as e:
        logger.error(f"매매 설정 로드 실패 — 기본값 사용: {e}")
        return dict(config.SHOP_DEFAULTS)


class ShopRoutineManager:
    """매매 루틴 실행과 주기(타이머)를 관리하는 객체.

    상태:
        enabled      : 매매 루틴 사용 여부 (config.json shop.enabled)
        interval     : 매매 주기(초)
        buy_quantity : 소모품 구매 수량
        _last_run    : 마지막 루틴 실행 monotonic 시각 (주기 판정용)
    """

    def __init__(self):
        """기본값으로 두고 config 는 reload() 시점에 로드한다."""
        self.enabled = config.SHOP_DEFAULTS['enabled']
        self.interval = float(config.SHOP_DEFAULTS['interval_sec'])
        self.buy_quantity = int(config.SHOP_DEFAULTS['buy_quantity'])
        self._last_run = None
        self.reload()

    def reload(self, path: str | None = None) -> None:
        """config.json 에서 매매 설정을 다시 읽어 상태를 갱신한다.

        Args:
            path: config.json 경로. None 이면 기본 경로.
        """
        try:
            cfg = load_shop_config(path)
            self.enabled = bool(cfg['enabled'])
            self.interval = float(cfg['interval_sec'])
            self.buy_quantity = int(cfg['buy_quantity'])
            logger.debug(
                f"매매 설정 로드 — enabled={self.enabled}, "
                f"interval={self.interval}s, buy_quantity={self.buy_quantity}"
            )
        except Exception as e:
            logger.error(f"매매 설정 갱신 실패: {e}")

    # ----- 주기(타이머) 제어 -----

    def reset(self, now: float | None = None) -> None:
        """주기 타이머를 현재 시각 기준으로 초기화한다 (매크로 시작 시 호출).

        시작 직후 곧바로 상점에 가지 않도록, 다음 실행은 한 주기(interval)
        뒤로 잡힌다.

        Args:
            now: 기준 monotonic 시각. None 이면 time.monotonic().
        """
        try:
            self._last_run = time.monotonic() if now is None else now
            logger.debug("매매 주기 타이머 초기화")
        except Exception as e:
            logger.error(f"매매 주기 초기화 실패: {e}")

    def is_due(self, now: float | None = None) -> bool:
        """매매 루틴을 실행할 때가 됐는지 판정한다.

        비활성이면 항상 False. 타이머가 초기화 안 됐으면 지금을 기준점으로
        잡고 False(한 주기 뒤부터 실행)를 반환한다.

        Args:
            now: 현재 monotonic 시각. None 이면 time.monotonic().

        Returns:
            마지막 실행 후 interval 이 지났으면 True.
        """
        try:
            if not self.enabled:
                return False
            if now is None:
                now = time.monotonic()
            if self._last_run is None:
                self._last_run = now
                return False
            return (now - self._last_run) >= self.interval
        except Exception as e:
            logger.error(f"매매 주기 판정 실패: {e}")
            return False

    def mark_ran(self, now: float | None = None) -> None:
        """루틴 실행 완료 시각을 기록해 다음 주기를 다시 센다.

        Args:
            now: 기준 monotonic 시각. None 이면 time.monotonic().
        """
        self._last_run = time.monotonic() if now is None else now

    # ----- 단계 실행 (모두 PREMIUM 전용) -----

    @staticmethod
    def _press_keys(sequence: list) -> None:
        """키 시퀀스를 순서대로 입력하고 각 키 뒤에 지터 딜레이를 둔다.

        Args:
            sequence: [(키, 기본딜레이(초)), ...] 형식의 키 시퀀스.
        """
        for key, base_delay in sequence:
            input_controller.press_key(key)
            delay = _jittered(base_delay)
            if delay > 0:
                time.sleep(delay)

    def _run_step(self, sequence: list, label: str) -> bool:
        """한 단계의 키 시퀀스를 실행하고 마무리 대기 후 결과를 반환한다.

        Args:
            sequence: 실행할 키 시퀀스.
            label: 로그에 표시할 단계 이름.

        Returns:
            성공 시 True, 예외 발생 시 False.
        """
        try:
            self._press_keys(sequence)
            time.sleep(random.uniform(
                config.SHOP_STEP_WAIT_MIN, config.SHOP_STEP_WAIT_MAX
            ))
            logger.info(f"매매 단계 완료: {label}")
            return True
        except Exception as e:
            logger.error(f"매매 단계 실패({label}): {e}")
            return False

    @require_tier('PREMIUM')
    def go_to_shop(self) -> bool:
        """상점/NPC 로 이동해 상점 창을 연다 (PREMIUM 전용).

        Returns:
            성공 여부.
        """
        return self._run_step(config.SHOP_GO_SEQUENCE, '상점 이동')

    @require_tier('PREMIUM')
    def sell_items(self) -> bool:
        """판매 탭에서 아이템을 일괄 판매한다 (PREMIUM 전용).

        Returns:
            성공 여부.
        """
        return self._run_step(config.SHOP_SELL_SEQUENCE, '판매')

    @require_tier('PREMIUM')
    def buy_consumables(self, quantity: int | None = None) -> bool:
        """구매 탭에서 소모품을 설정 수량만큼 구매한다 (PREMIUM 전용).

        구매 탭을 연 뒤 구매 확정 키를 quantity 회 반복 입력한다.

        Args:
            quantity: 구매 수량. None 이면 설정값(buy_quantity).

        Returns:
            성공 여부.
        """
        try:
            if quantity is None:
                quantity = self.buy_quantity
            quantity = max(0, int(quantity))

            self._press_keys(config.SHOP_BUY_OPEN_SEQUENCE)
            for _ in range(quantity):
                input_controller.press_key(config.SHOP_BUY_CONFIRM_KEY)
                time.sleep(random.uniform(
                    config.SHOP_BUY_ITEM_DELAY_MIN, config.SHOP_BUY_ITEM_DELAY_MAX
                ))
            time.sleep(random.uniform(
                config.SHOP_STEP_WAIT_MIN, config.SHOP_STEP_WAIT_MAX
            ))
            logger.info(f"매매 단계 완료: 구매 — {quantity}개")
            return True
        except Exception as e:
            logger.error(f"매매 단계 실패(구매): {e}")
            return False

    @require_tier('PREMIUM')
    def return_to_hunting(self) -> bool:
        """상점을 닫고 사냥터로 복귀한다 (PREMIUM 전용).

        Returns:
            성공 여부.
        """
        return self._run_step(config.SHOP_RETURN_SEQUENCE, '복귀')

    # ----- 오케스트레이터 -----

    def run_routine(self) -> dict:
        """매매 전체 흐름을 순서대로 실행한다 (이동→판매→구매→복귀).

        등급이 부족하면 첫 단계에서 PermissionError 가 발생하며, 이를
        밖으로 던지지 않고 denied=True 로 알린다(메인 루프 보호).
        한 단계라도 실패하면 즉시 중단한다.

        Returns:
            결과 딕셔너리:
                {'ok': bool, 'denied': bool, 'skipped': bool,
                 'steps': {단계명: bool, ...}}
        """
        result = {'ok': False, 'denied': False, 'skipped': False, 'steps': {}}
        try:
            if not self.enabled:
                logger.info("매매 루틴 비활성 — 건너뜀")
                result['ok'] = True
                result['skipped'] = True
                return result

            steps = (
                ('go', self.go_to_shop),
                ('sell', self.sell_items),
                ('buy', self.buy_consumables),
                ('return', self.return_to_hunting),
            )
            for name, fn in steps:
                ok = bool(fn())
                result['steps'][name] = ok
                if not ok:
                    logger.warning(f"매매 단계 실패({name}) — 루틴 중단")
                    return result

            result['ok'] = True
            logger.info("매매 루틴 완료 (이동→판매→구매→복귀)")
            return result
        except PermissionError as e:
            logger.warning(f"매매 루틴 권한 거부: {e}")
            result['denied'] = True
            return result
        except Exception as e:
            logger.error(f"매매 루틴 실행 실패: {e}")
            return result


# 프로그램 전역에서 공유하는 싱글톤 — 메인 루프에서 주기마다 호출한다
shop_manager = ShopRoutineManager()


def reload(path: str | None = None) -> None:
    """전역 shop_manager 설정을 다시 로드한다 (시작 시/설정 변경 후 호출)."""
    shop_manager.reload(path)


def run_shop_routine() -> dict:
    """전역 shop_manager.run_routine 의 단축 래퍼.

    Returns:
        run_routine 결과 딕셔너리.
    """
    return shop_manager.run_routine()
