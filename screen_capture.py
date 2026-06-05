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


def get_bar_ratio(region: dict, color_ranges: list, debug: bool = False) -> float | None:
    """가로 막대(HP/MP 바)의 채움 비율을 0~100(%) 으로 계산한다.

    바 영역을 캡처해 HSV 로 변환하고, 주어진 색상 범위에 해당하는
    픽셀 마스크를 만든다. 세로줄(column) 단위로 채움 여부를 판정해
    (채워진 줄 수 / 전체 줄 수) 비율을 반환한다. 가로 바는 왼쪽부터
    채워지므로 줄 기반 판정이 픽셀 단순 카운트보다 정확하다.

    Args:
        region: {'x','y','w','h'} 형식의 바 캡처 영역.
        color_ranges: [(lower, upper), ...] HSV 색상 범위 목록.
            빨강처럼 색상환 양끝에 걸친 경우 여러 범위를 합쳐 쓴다.
        debug: True 면 매칭 픽셀/줄 수를 로그로 출력한다.

    Returns:
        채움 비율(0.0~100.0). 캡처/분석 실패 시 None.
    """
    try:
        if not _CV2_AVAILABLE:
            logger.debug("[stub] get_bar_ratio — opencv 없음")
            return None

        img = capture_region(region)
        if img is None:
            logger.error("바 비율 계산 실패 — 캡처 이미지 없음")
            return None

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 여러 색상 범위를 OR 로 합쳐 하나의 마스크 생성
        mask = None
        for lower, upper in color_ranges:
            part = cv2.inRange(hsv, lower, upper)
            mask = part if mask is None else cv2.bitwise_or(mask, part)
        if mask is None:
            logger.error("바 비율 계산 실패 — 색상 범위가 비어있음")
            return None

        height, width = mask.shape[:2]
        if width == 0 or height == 0:
            logger.error("바 비율 계산 실패 — 영역 크기가 0")
            return None

        # 각 세로줄에서 색 픽셀이 임계 비율 이상이면 '채워짐'으로 판정
        col_match = (mask > 0).sum(axis=0)              # 줄별 매칭 픽셀 수
        threshold = config.BAR_COLUMN_FILL_RATIO * height
        filled_cols = int((col_match >= threshold).sum())
        ratio = (filled_cols / width) * 100.0

        if debug:
            logger.info(
                f"바 분석 — 매칭픽셀:{int((mask > 0).sum())} "
                f"채워진줄:{filled_cols}/{width} 비율:{ratio:.1f}%"
            )
        return ratio
    except Exception as e:
        logger.error(f"바 비율 계산 실패: {e}")
        return None


def get_hp_ratio(debug: bool = False) -> float | None:
    """현재 HP 바의 채움 비율(%)을 반환한다.

    Args:
        debug: True 면 분석 상세를 로그로 출력.

    Returns:
        HP 비율(0~100). 실패 시 None.
    """
    return get_bar_ratio(config.HP_BAR_REGION, config.HP_COLOR_RANGES, debug)


def get_mp_ratio(debug: bool = False) -> float | None:
    """현재 MP 바의 채움 비율(%)을 반환한다.

    Args:
        debug: True 면 분석 상세를 로그로 출력.

    Returns:
        MP 비율(0~100). 실패 시 None.
    """
    return get_bar_ratio(config.MP_BAR_REGION, config.MP_COLOR_RANGES, debug)


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
