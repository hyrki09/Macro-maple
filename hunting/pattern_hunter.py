"""패턴 방식 사냥 [FREE/BASIC/PREMIUM].

몬스터 위치를 탐지하지 않고, 미리 정해진 패턴대로 좌우 이동 + 층 이동 +
스킬 콤보를 반복한다. 미니맵 캐릭터 좌표(Y)로 현재 층을 판정해
층 이동 성공 여부를 확인하고, 실패하면 복구 루틴을 시도한다.

- 좌우 이동:   move_left_right()
- 층 이동:     move_to_floor(floor)
- 실패 재시도: floor_recovery()
- 전체 루프:   run_loop()  (BaseHunter 제공, step() 을 반복 호출)

모든 딜레이는 random.uniform (코드 규칙 2), 모든 키 입력은
input_controller 의 랜덤 딜레이를 거친다.
"""

import logging
import random
import time

import config
import input_controller
import macro_logic
import screen_capture

from .base_hunter import BaseHunter

logger = logging.getLogger(__name__)


class PatternHunter(BaseHunter):
    """타이머 기반 패턴 이동 사냥.

    상태:
        _direction    : 현재 좌우 이동 방향 ('left'/'right')
        _target_floor : 현재 사냥 중인 층
        _sweeps_done  : 현재 층에서 수행한 좌우 스윕 횟수
        _skill_mode   : 사용할 스킬 콤보 모드 (None 이면 config 기본값)
    """

    def __init__(self, skill_mode: str | None = None):
        """패턴 사냥 초기 상태를 설정한다.

        Args:
            skill_mode: 'highspec'/'lowspec'. None 이면 config.SKILL_MODE_DEFAULT.
                고스펙은 PREMIUM 전용이며, execute_skill_combo 가 등급을
                안전하게 처리한다(부족 시 denied).
        """
        self._direction = 'right'
        self._target_floor = config.PATTERN_FLOORS[0] if config.PATTERN_FLOORS else 1
        self._sweeps_done = 0
        self._skill_mode = skill_mode

    # ----- BaseHunter 인터페이스 구현 -----

    def find_monsters(self) -> list:
        """패턴 방식은 몬스터를 탐지하지 않으므로 항상 빈 리스트."""
        return []

    def decide_action(self, monsters: list) -> str:
        """내부 상태(스윕 횟수)를 보고 다음 행동을 결정한다.

        현재 층에서 정해진 횟수만큼 스윕했으면 'change_floor',
        아니면 'sweep' 을 반환한다.
        """
        try:
            if self._sweeps_done >= config.SWEEPS_PER_FLOOR:
                return 'change_floor'
            return 'sweep'
        except Exception as e:
            logger.error(f"행동 결정 실패: {e}")
            return 'sweep'

    def execute_action(self, action: str) -> None:
        """결정된 행동을 수행한다 ('sweep' / 'change_floor')."""
        try:
            if action == 'sweep':
                self._sweep()
            elif action == 'change_floor':
                self._change_floor()
            else:
                logger.warning(f"알 수 없는 패턴 행동: {action}")
        except Exception as e:
            logger.error(f"행동 실행 실패({action}): {e}")

    # ----- 패턴 동작 -----

    def _sweep(self) -> None:
        """현재 방향으로 한 번 이동하고 스킬 콤보를 쓴 뒤 방향을 뒤집는다."""
        self.move_left_right(self._direction)
        macro_logic.execute_skill_combo(self._skill_mode)
        self._direction = 'left' if self._direction == 'right' else 'right'
        self._sweeps_done += 1
        logger.debug(
            f"스윕 {self._sweeps_done}/{config.SWEEPS_PER_FLOOR} "
            f"(다음 방향:{self._direction}, 층:{self._target_floor})"
        )

    def _change_floor(self) -> None:
        """다른 층으로 이동한다. 실패하면 복구 후 한 번 더 시도한다."""
        target = self._other_floor(self._target_floor)
        ok = self.move_to_floor(target)
        if not ok:
            self.floor_recovery()
            ok = self.move_to_floor(target)
        if ok:
            self._target_floor = target
            logger.info(f"{target}층으로 이동 완료")
        else:
            logger.warning(f"{target}층 이동 최종 실패 — 현재 층 유지")
        # 성공/실패와 무관하게 스윕 카운터를 리셋해 다음 사이클을 시작
        self._sweeps_done = 0

    def move_left_right(self, direction: str | None = None,
                        hold: float | None = None) -> str:
        """지정한 방향으로 방향키를 hold 만큼 눌러 좌우 이동한다.

        Args:
            direction: 'left'/'right'. None 이면 현재 _direction.
            hold: 방향키 누름 시간(초). None 이면 config.MOVE_HOLD_MIN~MAX 랜덤.

        Returns:
            실제로 이동한 방향 문자열.
        """
        try:
            if direction is None:
                direction = self._direction
            key = (config.MOVE_LEFT_KEY if direction == 'left'
                   else config.MOVE_RIGHT_KEY)
            if hold is None:
                hold = random.uniform(config.MOVE_HOLD_MIN, config.MOVE_HOLD_MAX)
            input_controller.press_key(key, hold=hold)
            logger.debug(f"{direction} 이동 (hold:{hold:.2f}s)")
            return direction
        except Exception as e:
            logger.error(f"좌우 이동 실패({direction}): {e}")
            return direction or self._direction

    def _detect_floor(self) -> int | None:
        """미니맵 캐릭터 Y좌표로 현재 층을 판정한다.

        Returns:
            1 또는 2. 캐릭터 위치를 못 읽으면 None.
            (Y ≤ FLOOR2_Y_THRESHOLD → 미니맵 위쪽 = 2층)
        """
        try:
            pos = screen_capture.get_character_position()
            if pos is None:
                return None
            _, y = pos
            return 2 if y <= config.FLOOR2_Y_THRESHOLD else 1
        except Exception as e:
            logger.error(f"층 판정 실패: {e}")
            return None

    def move_to_floor(self, floor: int) -> bool:
        """목표 층으로 이동을 시도하고 미니맵으로 도달을 확인한다.

        목표가 위층이면 위 방향 + 점프, 아래층이면 아래 방향 + 점프를
        config.FLOOR_MOVE_ATTEMPTS 회까지 반복한다.

        Args:
            floor: 목표 층 (1/2).

        Returns:
            목표 층 도달 여부. 미니맵을 못 읽어도 최대한 시도 후 판정한다.
        """
        try:
            for attempt in range(1, config.FLOOR_MOVE_ATTEMPTS + 1):
                cur = self._detect_floor()
                if cur == floor:
                    logger.debug(f"{floor}층 도달 (시도 {attempt})")
                    return True
                self._jump_toward_floor(target=floor, current=cur)
                time.sleep(random.uniform(
                    config.FLOOR_MOVE_WAIT_MIN, config.FLOOR_MOVE_WAIT_MAX
                ))

            cur = self._detect_floor()
            reached = (cur == floor)
            if not reached:
                logger.warning(
                    f"{floor}층 이동 실패 — {config.FLOOR_MOVE_ATTEMPTS}회 시도 후 "
                    f"현재:{cur}"
                )
            return reached
        except Exception as e:
            logger.error(f"층 이동 실패({floor}): {e}")
            return False

    def _jump_toward_floor(self, target: int, current: int | None) -> None:
        """목표 층 방향(위/아래)으로 점프 입력을 한 번 보낸다.

        Args:
            target: 목표 층.
            current: 현재 층 (None 이면 위층으로 가정하고 위로 점프).
        """
        try:
            hold = random.uniform(
                config.FLOOR_MOVE_HOLD_MIN, config.FLOOR_MOVE_HOLD_MAX
            )
            going_up = (current is None) or (target > current)
            if going_up:
                # 위층: 위 방향 누른 채 점프 (사다리/포탈/점프 발판)
                input_controller.press_key(config.UP_KEY)
                input_controller.press_key(config.JUMP_KEY, hold=hold)
            else:
                # 아래층: 아래 방향 + 점프 (아래 점프)
                input_controller.press_key(config.DOWN_KEY)
                input_controller.press_key(config.JUMP_KEY, hold=hold)
        except Exception as e:
            logger.error(f"층 점프 입력 실패(target:{target}): {e}")

    def floor_recovery(self) -> None:
        """층 이동 실패 시 복구 — 반대 방향 끝으로 이동 후 한 번 점프한다.

        발판/사다리 진입 위치를 놓쳤을 때 위치를 재정렬하기 위한 동작이다.
        """
        try:
            logger.info("층 이동 복구 시도 — 위치 재정렬")
            recover_dir = 'left' if self._direction == 'right' else 'right'
            # 끝까지 확실히 가도록 최대 hold 로 이동
            self.move_left_right(recover_dir, hold=config.MOVE_HOLD_MAX)
            input_controller.press_key(config.JUMP_KEY)
            time.sleep(random.uniform(
                config.FLOOR_MOVE_WAIT_MIN, config.FLOOR_MOVE_WAIT_MAX
            ))
        except Exception as e:
            logger.error(f"층 이동 복구 실패: {e}")

    @staticmethod
    def _other_floor(floor: int) -> int:
        """PATTERN_FLOORS 목록에서 현재 층이 아닌 다른 층을 반환한다.

        층이 2개뿐인 보통 상황에서 1↔2 를 토글한다. 목록에 다른 층이
        없으면 현재 층을 그대로 반환한다.
        """
        others = [f for f in config.PATTERN_FLOORS if f != floor]
        return others[0] if others else floor
