"""사냥 루틴 공통 인터페이스 (추상 클래스).

모든 사냥 방식(패턴/YOLO)은 BaseHunter 를 상속해
find_monsters / decide_action / execute_action 세 가지를 구현한다.
공통 루프(run_loop)와 1회전 동작(step)은 베이스에서 제공한다.
(코드 규칙 1: 한국어 docstring, 6: 예외처리 필수)
"""

import logging
import random
import time
from abc import ABC, abstractmethod

import config

logger = logging.getLogger(__name__)


class BaseHunter(ABC):
    """모든 사냥 방식이 상속받는 추상 클래스."""

    @abstractmethod
    def find_monsters(self) -> list:
        """현재 화면에서 몬스터 위치 목록을 반환한다.

        패턴 방식은 탐지가 없어 빈 리스트를, YOLO 방식은 바운딩박스
        좌표 리스트를 반환한다.
        """
        raise NotImplementedError

    @abstractmethod
    def decide_action(self, monsters: list) -> str:
        """몬스터 목록/내부 상태를 보고 다음 행동(문자열)을 결정한다."""
        raise NotImplementedError

    @abstractmethod
    def execute_action(self, action: str) -> None:
        """decide_action 이 반환한 행동을 실제로 수행한다."""
        raise NotImplementedError

    def step(self) -> str:
        """사냥 루프 1회전 — 탐지 → 판단 → 실행을 한 번 수행한다.

        메인 루프가 매 틱마다 호출할 수 있도록 비차단 1회 동작으로 분리했다.

        Returns:
            이번에 실행한 행동 문자열. 실패 시 'error'.
        """
        try:
            monsters = self.find_monsters()
            action = self.decide_action(monsters)
            self.execute_action(action)
            return action
        except Exception as e:
            logger.error(f"사냥 step 실패: {e}")
            return 'error'

    def run_loop(self, should_continue=None, max_steps: int | None = None) -> int:
        """공통 사냥 루프 — 두 방식 모두 동일하게 사용한다.

        Args:
            should_continue: 인자 없는 콜러블. False 를 반환하면 루프 종료.
                None 이면 max_steps 에 도달할 때까지(또는 무한) 돈다.
                (메인 앱의 running 플래그 / 종료 이벤트를 연결하는 용도)
            max_steps: 최대 반복 횟수. None 이면 제한 없음. (테스트/안전장치)

        Returns:
            실제로 수행한 step 횟수.
        """
        steps = 0
        try:
            while True:
                if should_continue is not None and not should_continue():
                    break
                if max_steps is not None and steps >= max_steps:
                    break
                self.step()
                steps += 1
                # 코드 규칙 2: 루프 딜레이도 랜덤
                time.sleep(random.uniform(
                    config.DELAY_LOOP_MIN, config.DELAY_LOOP_MAX
                ))
            return steps
        except Exception as e:
            logger.error(f"사냥 루프 오류: {e}")
            return steps
