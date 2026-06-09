"""사용자 설정(config.json) 읽기/쓰기 모듈 (PHASE 10).

config.json 전체를 기본값과 병합해 로드하고, 설정 UI 가 수정한 값을 다시
저장한다. telegram / shop 블록은 각 모듈(telegram_bot / shop_routine)이
자기 블록만 따로 읽어 쓰므로, 여기서는 같은 파일을 통째로 읽고 쓰며
기본값을 채우는 역할을 한다. (코드 규칙 3: 설정은 config 에서, 6: 예외처리)

구조(config.json):
    {
      "license_key": "",
      "hunt_mode": "pattern",
      "map": "red_elephant_2",
      "skill_mode": "lowspec",
      "pet_feed_interval": 600,
      "teleport_interval": 300,
      "telegram": { "enabled": false, "token": "", "chat_id": "" },
      "shop": { "enabled": true, "interval_sec": 1800, "buy_quantity": 30 }
    }
"""

import json
import logging
import os

import config

logger = logging.getLogger(__name__)


def default_config() -> dict:
    """기본값으로 채운 전체 설정 딕셔너리를 새로 만들어 반환한다.

    telegram / shop 블록은 각 모듈의 *_DEFAULTS 를 복사해 단일 출처를 유지한다.

    Returns:
        모든 키가 채워진 설정 딕셔너리(깊은 복사).
    """
    cfg = dict(config.USER_CONFIG_DEFAULTS)
    cfg[config.TELEGRAM_CONFIG_KEY] = dict(config.TELEGRAM_DEFAULTS)
    cfg[config.SHOP_CONFIG_KEY] = dict(config.SHOP_DEFAULTS)
    return cfg


def _merge(base: dict, override: dict) -> dict:
    """base(기본값) 위에 override(파일값)를 한 단계 깊이까지 병합한다.

    중첩 딕셔너리(telegram/shop)는 키 단위로 덮어쓰고, 그 외는 값을 교체한다.
    base 에 없는(알 수 없는) 키도 보존해, 미래 버전의 추가 설정을 잃지 않는다.

    Args:
        base: 기본값 딕셔너리.
        override: 파일에서 읽은 사용자 값.

    Returns:
        병합된 새 딕셔너리.
    """
    result = dict(base)
    for key, val in override.items():
        if (key in result and isinstance(result[key], dict)
                and isinstance(val, dict)):
            merged = dict(result[key])
            merged.update(val)
            result[key] = merged
        else:
            result[key] = val
    return result


def load_config(path: str | None = None) -> dict:
    """config.json 을 읽어 기본값과 병합한 전체 설정을 반환한다.

    파일이 없거나 손상됐으면 기본값을 그대로 반환한다(안전).

    Args:
        path: config.json 경로. None 이면 config.CONFIG_JSON_PATH.

    Returns:
        기본값이 모두 채워진 설정 딕셔너리.
    """
    base = default_config()
    try:
        if path is None:
            path = config.CONFIG_JSON_PATH
        if not os.path.exists(path):
            logger.debug(f"config.json 없음 — 기본 설정 사용: {path}")
            return base
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.error("config.json 형식 오류(최상위가 객체 아님) — 기본 설정 사용")
            return base
        return _merge(base, data)
    except Exception as e:
        logger.error(f"설정 로드 실패 — 기본 설정 사용: {e}")
        return base


def save_config(data: dict, path: str | None = None) -> bool:
    """설정 딕셔너리를 config.json 에 저장한다 (UTF-8, 들여쓰기, 한글 보존).

    Args:
        data: 저장할 전체 설정 딕셔너리.
        path: config.json 경로. None 이면 config.CONFIG_JSON_PATH.

    Returns:
        저장 성공 여부.
    """
    try:
        if path is None:
            path = config.CONFIG_JSON_PATH
        # 디렉터리가 지정돼 있으면 보장 (기본은 현재 폴더라 보통 불필요)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"설정 저장됨: {path}")
        return True
    except Exception as e:
        logger.error(f"설정 저장 실패: {e}")
        return False
