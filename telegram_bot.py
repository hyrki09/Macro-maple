"""텔레그램 알림 모듈 (PHASE 8).

매크로 시작/중지/이상상황 발생 시 텔레그램으로 메시지와 스크린샷을 보낸다.

설계 메모
  - 토큰/채팅ID 는 코드에 두지 않고 config.json 의 telegram 블록에서 로드한다.
    (config.json 은 .gitignore 로 커밋에서 제외됨)
  - 전송은 requests 로 텔레그램 Bot HTTP API(sendMessage / sendPhoto)를 직접
    호출한다. (requests 는 이미 의존성에 포함, 동기 API 라 테스트하기 쉽다)
  - 메인 루프를 막지 않도록 *_async 래퍼가 데몬 스레드로 전송한다.
  - 알림은 전 등급(FREE 포함) 기능이므로 라이선스 체크가 없다.

(코드 규칙 1: 한국어 docstring, 3: 설정은 config 에서, 6: 예외처리 필수,
 7: logging 사용)
"""

import json
import logging
import os
import threading

import config
import screen_capture

logger = logging.getLogger(__name__)

try:
    import requests
    _REQUESTS_AVAILABLE = True
except Exception as e:  # pragma: no cover - 환경에 따라 다름
    requests = None
    _REQUESTS_AVAILABLE = False
    logger.warning(f"requests 임포트 실패 — 텔레그램 알림 비활성화: {e}")

try:
    import cv2
    _CV2_AVAILABLE = True
except Exception as e:  # pragma: no cover - 환경에 따라 다름
    cv2 = None
    _CV2_AVAILABLE = False


def load_telegram_config(path: str | None = None) -> dict:
    """config.json 에서 telegram 설정 블록을 읽어 반환한다.

    파일이 없거나 telegram 블록이 없으면 TELEGRAM_DEFAULTS 로 채운다.
    (최초 실행/미설정 시 알림은 안전하게 비활성 상태가 된다)

    Args:
        path: config.json 경로. None 이면 config.CONFIG_JSON_PATH.

    Returns:
        {'enabled', 'token', 'chat_id'} 키를 가진 설정 딕셔너리.
    """
    cfg = dict(config.TELEGRAM_DEFAULTS)
    try:
        if path is None:
            path = config.CONFIG_JSON_PATH
        if not os.path.exists(path):
            logger.debug(f"config.json 없음 — 텔레그램 기본값 사용: {path}")
            return cfg
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        block = data.get(config.TELEGRAM_CONFIG_KEY, {})
        if isinstance(block, dict):
            cfg.update({k: block[k] for k in cfg if k in block})
        return cfg
    except Exception as e:
        logger.error(f"텔레그램 설정 로드 실패 — 기본값 사용: {e}")
        return cfg


class TelegramNotifier:
    """config.json 의 토큰/채팅ID 로 텔레그램 알림을 전송하는 객체.

    상태:
        enabled : 알림 사용 여부 (config.json telegram.enabled)
        token   : BotFather 발급 봇 토큰
        chat_id : 알림 받을 채팅 ID
    """

    def __init__(self):
        """기본 비활성 상태로 두고, config 는 reload() 시점에 로드한다."""
        self.enabled = False
        self.token = ''
        self.chat_id = ''
        self.reload()

    def reload(self, path: str | None = None) -> None:
        """config.json 에서 텔레그램 설정을 다시 읽어 상태를 갱신한다.

        Args:
            path: config.json 경로. None 이면 기본 경로.
        """
        try:
            cfg = load_telegram_config(path)
            self.enabled = bool(cfg.get('enabled', False))
            self.token = str(cfg.get('token', '') or '')
            self.chat_id = str(cfg.get('chat_id', '') or '')
            logger.debug(
                f"텔레그램 설정 로드 — enabled={self.enabled}, "
                f"configured={self.is_configured()}"
            )
        except Exception as e:
            logger.error(f"텔레그램 설정 갱신 실패: {e}")

    def is_configured(self) -> bool:
        """알림을 보낼 수 있는 상태인지(활성 + 토큰/ID + requests) 확인한다.

        Returns:
            전송 가능하면 True.
        """
        return bool(
            _REQUESTS_AVAILABLE and self.enabled
            and self.token and self.chat_id
        )

    # ----- 저수준 전송 -----

    def _api_request(self, method: str, data: dict,
                     files: dict | None = None) -> bool:
        """텔레그램 Bot API 메서드를 호출한다 (공용 전송 헬퍼).

        테스트에서는 이 메서드를 가로채(mock) 네트워크 없이 검증한다.

        Args:
            method: API 메서드명 (예: 'sendMessage', 'sendPhoto').
            data: 폼 데이터 (chat_id, text 등).
            files: 첨부 파일 딕셔너리. 없으면 None.

        Returns:
            전송 성공(HTTP 200 + ok=True)이면 True.
        """
        try:
            url = f"{config.TELEGRAM_API_BASE}/bot{self.token}/{method}"
            resp = requests.post(
                url, data=data, files=files,
                timeout=config.TELEGRAM_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.error(
                    f"텔레그램 {method} 실패 — HTTP {resp.status_code}: "
                    f"{resp.text[:200]}"
                )
                return False
            body = resp.json()
            if not body.get('ok', False):
                logger.error(f"텔레그램 {method} 실패 — 응답: {body}")
                return False
            return True
        except Exception as e:
            logger.error(f"텔레그램 {method} 요청 실패: {e}")
            return False

    # ----- 고수준 전송 -----

    def send_message(self, text: str) -> bool:
        """텍스트 메시지를 전송한다.

        Args:
            text: 보낼 메시지 문자열.

        Returns:
            전송 성공이면 True. 미설정/실패 시 False.
        """
        try:
            if not self.is_configured():
                logger.debug("텔레그램 미설정 — 메시지 전송 건너뜀")
                return False
            data = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': config.TELEGRAM_PARSE_MODE,
            }
            ok = self._api_request('sendMessage', data)
            if ok:
                logger.info(f"텔레그램 메시지 전송: {text}")
            return ok
        except Exception as e:
            logger.error(f"텔레그램 메시지 전송 실패: {e}")
            return False

    def send_screenshot(self, caption: str | None = None) -> bool:
        """현재 전체 화면을 캡처해 스크린샷으로 전송한다.

        캡처/인코딩에 실패하면 가능한 경우 caption 만 텍스트로 보낸다.

        Args:
            caption: 사진에 붙일 설명. None 이면 설명 없이 전송.

        Returns:
            사진 전송 성공이면 True. 미설정/실패 시 False.
        """
        try:
            if not self.is_configured():
                logger.debug("텔레그램 미설정 — 스크린샷 전송 건너뜀")
                return False

            png = self._capture_png()
            if png is None:
                logger.warning("스크린샷 인코딩 실패 — 텍스트로 대체 전송")
                if caption:
                    return self.send_message(caption)
                return False

            data = {'chat_id': self.chat_id}
            if caption:
                data['caption'] = caption
            files = {'photo': ('screenshot.png', png, 'image/png')}
            ok = self._api_request('sendPhoto', data, files=files)
            if ok:
                logger.info(f"텔레그램 스크린샷 전송: {caption or '(설명 없음)'}")
            return ok
        except Exception as e:
            logger.error(f"텔레그램 스크린샷 전송 실패: {e}")
            return False

    @staticmethod
    def _capture_png() -> bytes | None:
        """전체 화면을 캡처해 PNG 바이트로 인코딩한다.

        Returns:
            PNG 바이트열. 캡처/인코딩 실패 시 None.
        """
        try:
            if not _CV2_AVAILABLE:
                logger.error("스크린샷 인코딩 실패 — opencv 없음")
                return None
            img = screen_capture.capture_full_screen()
            if img is None:
                logger.error("스크린샷 캡처 실패 — 이미지 없음")
                return None
            ok, buf = cv2.imencode('.png', img)
            if not ok:
                logger.error("스크린샷 PNG 인코딩 실패")
                return None
            return buf.tobytes()
        except Exception as e:
            logger.error(f"스크린샷 캡처/인코딩 실패: {e}")
            return None

    # ----- 비동기(백그라운드) 전송 -----

    def _run_async(self, fn, *args) -> None:
        """전송 함수를 데몬 스레드로 실행해 메인 루프를 막지 않는다.

        미설정 상태면 스레드 생성 비용도 들이지 않고 바로 반환한다.
        """
        try:
            if not self.is_configured():
                return
            t = threading.Thread(target=fn, args=args, daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"텔레그램 비동기 전송 실패: {e}")

    def send_message_async(self, text: str) -> None:
        """텍스트 메시지를 백그라운드로 전송한다 (논블로킹)."""
        self._run_async(self.send_message, text)

    def send_screenshot_async(self, caption: str | None = None) -> None:
        """스크린샷을 백그라운드로 전송한다 (논블로킹)."""
        self._run_async(self.send_screenshot, caption)


# 프로그램 전역에서 공유하는 싱글톤 — main 에서 이벤트마다 호출한다
notifier = TelegramNotifier()


def reload(path: str | None = None) -> None:
    """전역 notifier 설정을 다시 로드한다 (시작 시/설정 변경 후 호출)."""
    notifier.reload(path)


def notify_start() -> None:
    """매크로 시작 알림을 백그라운드로 전송한다."""
    notifier.send_message_async(config.MSG_MACRO_START)


def notify_stop() -> None:
    """매크로 중지 알림을 백그라운드로 전송한다."""
    notifier.send_message_async(config.MSG_MACRO_STOP)


def notify_alert(reasons) -> None:
    """비정상 상태 알림 + 스크린샷을 백그라운드로 전송한다.

    Args:
        reasons: 감지 사유. 문자열 또는 문자열 리스트.
    """
    try:
        if isinstance(reasons, (list, tuple)):
            reasons = ', '.join(str(r) for r in reasons)
        text = config.MSG_MACRO_ALERT.format(reasons=reasons)
        # 이상상황은 화면 증거가 중요하므로 스크린샷에 설명을 붙여 보낸다
        notifier.send_screenshot_async(text)
    except Exception as e:
        logger.error(f"비정상 상태 알림 전송 실패: {e}")
