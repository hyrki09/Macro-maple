"""화면 캡처 + OpenCV 분석 모듈.

mss 로 화면을 캡처하고 numpy/OpenCV 로 분석한다.
PHASE 1 단계에서는 전체화면 캡처 및 디버그 저장 기능만 제공한다.
(코드 규칙 4: 화면 인식은 OpenCV + YOLOv8 만 사용)
"""

import logging
import os
import time

import numpy as np

import config

logger = logging.getLogger(__name__)

try:
    import mss
    _MSS_AVAILABLE = True
except Exception as e:
    logger.warning(f"mss 임포트 실패 — 화면 캡처 비활성화: {e}")
    _MSS_AVAILABLE = False

try:
    import cv2
    _CV2_AVAILABLE = True
except Exception as e:
    logger.warning(f"opencv 임포트 실패 — 이미지 저장 비활성화: {e}")
    _CV2_AVAILABLE = False


def capture_region(region: dict) -> np.ndarray | None:
    """지정한 화면 영역을 캡처해 BGR numpy 배열로 반환한다.

    Args:
        region: {'x', 'y', 'w', 'h'} 형식의 캡처 영역.

    Returns:
        BGR 이미지 배열. 캡처 실패 시 None.
    """
    try:
        if not _MSS_AVAILABLE:
            logger.debug("[stub] capture_region — mss 없음")
            return None
        monitor = {
            'left': region['x'], 'top': region['y'],
            'width': region['w'], 'height': region['h'],
        }
        with mss.mss() as sct:
            shot = sct.grab(monitor)
        # mss 는 BGRA 로 반환 → BGR 로 변환
        img = np.array(shot)[:, :, :3]
        return img
    except Exception as e:
        logger.error(f"화면 캡처 실패: {e}")
        return None


def capture_full_screen() -> np.ndarray | None:
    """전체 화면(1920x1080 기준)을 캡처해 반환한다."""
    return capture_region(config.FULL_SCREEN_REGION)


def save_debug_capture(filename: str | None = None) -> str | None:
    """현재 전체 화면을 캡처해 captures/ 폴더에 저장한다. (PHASE 1 동작 확인용)

    Args:
        filename: 저장할 파일명. None 이면 타임스탬프로 자동 생성.

    Returns:
        저장된 파일 경로. 실패 시 None.
    """
    try:
        img = capture_full_screen()
        if img is None:
            logger.error("디버그 캡처 실패 — 이미지 없음")
            return None
        if not _CV2_AVAILABLE:
            logger.error("디버그 캡처 저장 실패 — opencv 없음")
            return None

        os.makedirs(config.CAPTURE_DIR, exist_ok=True)
        if filename is None:
            filename = f"debug_{int(time.time())}.png"
        path = os.path.join(config.CAPTURE_DIR, filename)
        cv2.imwrite(path, img)
        logger.info(f"디버그 캡처 저장됨: {path}")
        return path
    except Exception as e:
        logger.error(f"디버그 캡처 저장 실패: {e}")
        return None
