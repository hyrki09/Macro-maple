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


# 템플릿 이미지 디스크 캐시 — 경로별로 한 번만 읽는다. None 은 '읽기 실패' 표시.
_template_cache: dict = {}


def load_template(path: str, use_cache: bool = True) -> np.ndarray | None:
    """템플릿 이미지를 디스크에서 BGR 배열로 읽는다 (경로별 캐시).

    Args:
        path: 템플릿 이미지 파일 경로.
        use_cache: True 면 같은 경로를 다시 읽지 않고 캐시를 쓴다.

    Returns:
        BGR 이미지 배열. 파일이 없거나 읽기 실패 시 None.
    """
    try:
        if not _CV2_AVAILABLE:
            logger.debug("[stub] load_template — opencv 없음")
            return None
        if use_cache and path in _template_cache:
            return _template_cache[path]

        if not os.path.exists(path):
            logger.warning(
                f"템플릿 이미지 없음: {path} — 실제 게임 미니맵에서 캐릭터 점을 "
                f"잘라 이 경로에 저장하세요."
            )
            if use_cache:
                _template_cache[path] = None
            return None

        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            logger.error(f"템플릿 이미지 읽기 실패(손상?): {path}")
            if use_cache:
                _template_cache[path] = None
            return None

        if use_cache:
            _template_cache[path] = img
        return img
    except Exception as e:
        logger.error(f"템플릿 로드 실패({path}): {e}")
        return None


def find_template(image: np.ndarray, template: np.ndarray,
                  threshold: float | None = None,
                  debug: bool = False) -> dict | None:
    """image 안에서 template 의 최적 매칭 위치를 찾는다 (TM_CCOEFF_NORMED).

    Args:
        image: 검색 대상 BGR 이미지.
        template: 찾을 BGR 템플릿 이미지 (image 보다 작아야 한다).
        threshold: 매칭 점수 하한(0~1). None 이면 config.TEMPLATE_MATCH_THRESHOLD.
        debug: True 면 매칭 점수(max_val)를 로그로 출력.

    Returns:
        매칭 정보 딕셔너리. 점수가 threshold 미만이거나 실패 시 None.
            {'score': float, 'top_left': (x, y),
             'center': (cx, cy), 'size': (w, h)}
        좌표는 모두 image 기준 픽셀 좌표.
    """
    try:
        if not _CV2_AVAILABLE:
            logger.debug("[stub] find_template — opencv 없음")
            return None
        if image is None or template is None:
            logger.error("템플릿 매칭 실패 — 입력 이미지/템플릿이 None")
            return None
        if threshold is None:
            threshold = config.TEMPLATE_MATCH_THRESHOLD

        ih, iw = image.shape[:2]
        th, tw = template.shape[:2]
        if th > ih or tw > iw:
            logger.error(
                f"템플릿 매칭 실패 — 템플릿({tw}x{th})이 대상({iw}x{ih})보다 큼"
            )
            return None

        res = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if debug:
            logger.info(f"템플릿 매칭 — max_val:{max_val:.3f} (임계값:{threshold})")

        if max_val < threshold:
            return None

        top_left = (int(max_loc[0]), int(max_loc[1]))
        center = (top_left[0] + tw // 2, top_left[1] + th // 2)
        return {
            'score': float(max_val),
            'top_left': top_left,
            'center': center,
            'size': (tw, th),
        }
    except Exception as e:
        logger.error(f"템플릿 매칭 실패: {e}")
        return None


def get_character_position(template: np.ndarray | None = None,
                           region: dict | None = None,
                           threshold: float | None = None,
                           debug: bool = False) -> tuple[int, int] | None:
    """미니맵에서 캐릭터 점을 찾아 미니맵 내 (x, y) 좌표를 반환한다.

    미니맵 영역을 캡처하고 캐릭터 점 템플릿으로 매칭해, 매칭된 점의
    중심을 미니맵 기준 좌표로 돌려준다. 캐릭터가 이동하면 이 좌표가
    실시간으로 바뀐다. (PHASE 6 층 이동 판정 등에서 사용)

    Args:
        template: 캐릭터 점 BGR 템플릿. None 이면 config.MINIMAP_TEMPLATE_PATH 에서 로드.
        region: 미니맵 캡처 영역 {'x','y','w','h'}. None 이면 config.MINIMAP_REGION.
        threshold: 매칭 임계값(0~1). None 이면 config.MINIMAP_MATCH_THRESHOLD.
        debug: True 면 매칭 점수를 로그로 출력.

    Returns:
        미니맵 좌상단(0,0) 기준 캐릭터 (x, y) 좌표. 못 찾으면 None.
    """
    try:
        if region is None:
            region = config.MINIMAP_REGION
        if threshold is None:
            threshold = config.MINIMAP_MATCH_THRESHOLD
        if template is None:
            template = load_template(config.MINIMAP_TEMPLATE_PATH)
        if template is None:
            # load_template 이 이미 안내 로그를 남겼다
            return None

        minimap = capture_region(region)
        if minimap is None:
            logger.error("캐릭터 위치 인식 실패 — 미니맵 캡처 없음")
            return None

        match = find_template(minimap, template, threshold=threshold, debug=debug)
        if match is None:
            if debug:
                logger.info("캐릭터 점을 찾지 못함 (매칭 점수 부족)")
            return None

        pos = match['center']
        if debug:
            logger.info(f"캐릭터 위치 — x:{pos[0]} y:{pos[1]} (점수:{match['score']:.3f})")
        return pos
    except Exception as e:
        logger.error(f"캐릭터 위치 인식 실패: {e}")
        return None


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
