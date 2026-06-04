"""키보드/마우스 입력 제어 모듈.

모든 입력은 사람처럼 보이도록 random.uniform 기반 랜덤 딜레이를 넣는다.
(코드 규칙 2: 고정 딜레이 금지)
PHASE 1 단계에서는 키 입력 함수 뼈대만 제공한다.
"""

import logging
import random
import time

import config

logger = logging.getLogger(__name__)

try:
    import pyautogui
    # 코드 규칙: FAILSAFE 항상 유지 (마우스를 좌상단으로 옮기면 비상 정지)
    pyautogui.FAILSAFE = True
    _PYAUTOGUI_AVAILABLE = True
except Exception as e:  # pyautogui 미설치/임포트 실패 시에도 프로그램은 떠야 한다
    logger.warning(f"pyautogui 임포트 실패 — 키 입력 비활성화: {e}")
    _PYAUTOGUI_AVAILABLE = False


def random_key_delay() -> float:
    """키 입력 사이에 쓸 랜덤 딜레이(초)를 반환한다."""
    return random.uniform(config.DELAY_KEY_MIN, config.DELAY_KEY_MAX)


def press_key(key: str, hold: float | None = None) -> None:
    """키 한 개를 누른다. hold 지정 시 그 시간만큼 눌렀다 뗀다.

    Args:
        key: 누를 키 이름 (예: 'z', '1', 'left').
        hold: 키를 누르고 있을 시간(초). None 이면 짧게 탭.
    """
    try:
        if not _PYAUTOGUI_AVAILABLE:
            logger.debug(f"[stub] press_key({key}) — pyautogui 없음")
            return
        if hold is None:
            pyautogui.press(key)
        else:
            pyautogui.keyDown(key)
            time.sleep(hold)
            pyautogui.keyUp(key)
        time.sleep(random_key_delay())
    except Exception as e:
        logger.error(f"키 입력 실패 ({key}): {e}")


def press_sequence(keys: list[str]) -> None:
    """키 목록을 순서대로 입력한다. 각 입력 사이 랜덤 딜레이가 들어간다.

    Args:
        keys: 순서대로 누를 키 이름 리스트.
    """
    try:
        for key in keys:
            press_key(key)
    except Exception as e:
        logger.error(f"키 시퀀스 입력 실패: {e}")
