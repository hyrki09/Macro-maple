"""게임 매크로 진입점.

PHASE 1: 핫키 등록과 메인 루프 뼈대.
  - F9  : 매크로 시작/중지 토글
  - F10 : 프로그램 완전 종료

실제 사냥 로직은 이후 PHASE 에서 메인 루프 안에 연결한다.
관리자 권한으로 실행해야 키 입력이 게임에 전달된다. (트러블슈팅 참고)
"""

import logging
import random
import threading
import time

import config
import screen_capture

try:
    import keyboard
    _KEYBOARD_AVAILABLE = True
except Exception as e:
    keyboard = None
    _KEYBOARD_AVAILABLE = False


logger = logging.getLogger(__name__)


class MacroApp:
    """매크로 전체 상태와 메인 루프를 관리하는 클래스."""

    def __init__(self):
        """앱 상태 초기화 — 실행 여부 플래그와 종료 이벤트 준비."""
        self.running = False              # 매크로 사냥 동작 중 여부 (F9 토글)
        self._stop_event = threading.Event()  # 프로그램 종료 신호 (F10)

    def toggle(self) -> None:
        """F9 핸들러 — 매크로 시작/중지를 토글한다."""
        try:
            self.running = not self.running
            state = "시작" if self.running else "중지"
            logger.info(f"매크로 {state} (F9)")
        except Exception as e:
            logger.error(f"토글 처리 실패: {e}")

    def shutdown(self) -> None:
        """F10 핸들러 — 메인 루프를 빠져나가도록 종료 신호를 보낸다."""
        try:
            logger.info("종료 요청 (F10)")
            self.running = False
            self._stop_event.set()
        except Exception as e:
            logger.error(f"종료 처리 실패: {e}")

    def register_hotkeys(self) -> bool:
        """F9/F10 핫키를 등록한다.

        Returns:
            등록 성공 여부. keyboard 모듈이 없으면 False.
        """
        try:
            if not _KEYBOARD_AVAILABLE:
                logger.error(
                    "keyboard 모듈이 없어 핫키를 등록할 수 없습니다. "
                    "'pip install keyboard' 후 관리자 권한으로 실행하세요."
                )
                return False
            keyboard.add_hotkey(config.HOTKEY_TOGGLE, self.toggle)
            keyboard.add_hotkey(config.HOTKEY_EXIT, self.shutdown)
            logger.info(
                f"핫키 등록 완료 — 시작/중지: {config.HOTKEY_TOGGLE.upper()}, "
                f"종료: {config.HOTKEY_EXIT.upper()}"
            )
            return True
        except Exception as e:
            logger.error(f"핫키 등록 실패: {e}")
            return False

    def run(self) -> None:
        """메인 루프 — 종료 신호가 올 때까지 돈다.

        running 이 True 일 때만 실제 사냥 동작을 수행한다.
        PHASE 1 에서는 동작 자리만 비워두고 루프만 유지한다.
        """
        try:
            logger.info("메인 루프 시작 — F9 로 사냥 시작/중지, F10 으로 종료")
            while not self._stop_event.is_set():
                if self.running:
                    self._tick()
                # 코드 규칙 2: 루프 딜레이도 랜덤
                time.sleep(random.uniform(
                    config.DELAY_LOOP_MIN, config.DELAY_LOOP_MAX
                ))
        except KeyboardInterrupt:
            logger.info("키보드 인터럽트로 종료")
        except Exception as e:
            logger.error(f"메인 루프 오류: {e}")
        finally:
            logger.info("메인 루프 종료")

    def _tick(self) -> None:
        """메인 루프 1회전 동작. PHASE 1 은 자리만 차지하는 stub.

        이후 PHASE 에서 포션 체크 / 사냥 루프 / 상태 감시를 여기에 연결한다.
        """
        try:
            # TODO(PHASE 3+): check_and_use_potion(), hunter.run_loop() 등 연결
            pass
        except Exception as e:
            logger.error(f"_tick 처리 실패: {e}")


def setup_logging() -> None:
    """로깅 기본 설정 — 코드 규칙 7: print 대신 logging 사용."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format=config.LOG_FORMAT,
    )


def main() -> None:
    """프로그램 진입점 — 로깅 설정, 핫키 등록, 메인 루프 실행."""
    setup_logging()
    logger.info("===== 메이플 자동사냥 매크로 시작 =====")

    app = MacroApp()
    if not app.register_hotkeys():
        logger.error("핫키 등록에 실패하여 종료합니다.")
        return

    app.run()
    logger.info("===== 프로그램 정상 종료 =====")


if __name__ == '__main__':
    main()
