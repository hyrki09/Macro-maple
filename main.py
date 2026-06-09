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
import macro_logic
import monitor
import screen_capture
import telegram_bot
from hunting.pattern_hunter import PatternHunter
from license.license_manager import license_manager

try:
    import keyboard
    _KEYBOARD_AVAILABLE = True
except Exception as e:
    keyboard = None
    _KEYBOARD_AVAILABLE = False


logger = logging.getLogger(__name__)


def create_hunter():
    """설정 + 라이선스에 따라 사냥 방식을 결정해 인스턴스를 반환한다.

    PHASE 6 에서는 패턴 방식(PatternHunter)만 제공한다.
    PHASE 11 에서 YOLO 방식 분기를 추가한다:
        mode == 'yolo' and license_manager.is_allowed('PREMIUM') → YoloHunter

    Returns:
        BaseHunter 구현 인스턴스.
    """
    try:
        # TODO(PHASE 11): config.json 의 hunt_mode + PREMIUM 검사로 YoloHunter 분기
        return PatternHunter()
    except Exception as e:
        logger.error(f"사냥 방식 생성 실패 — 패턴 방식으로 진행: {e}")
        return PatternHunter()


class MacroApp:
    """매크로 전체 상태와 메인 루프를 관리하는 클래스."""

    def __init__(self):
        """앱 상태 초기화 — 실행 여부 플래그와 종료 이벤트 준비."""
        self.running = False              # 매크로 사냥 동작 중 여부 (F9 토글)
        self._stop_event = threading.Event()  # 프로그램 종료 신호 (F10)
        self.hunter = create_hunter()     # PHASE 6: 사냥 방식 (현재 패턴 방식)
        self.monitor = monitor.state_monitor  # PHASE 7: 상태 감시 싱글톤

    def toggle(self) -> None:
        """F9 핸들러 — 매크로 시작/중지를 토글한다."""
        try:
            self.running = not self.running
            state = "시작" if self.running else "중지"
            logger.info(f"매크로 {state} (F9)")
            # PHASE 7: 시작/재개 시 누적된 감시 상태(정지/반복 기록)를 초기화
            # PHASE 8: 시작/중지 시 텔레그램 알림 (논블로킹)
            if self.running:
                self.monitor.reset()
                telegram_bot.notify_start()
            else:
                telegram_bot.notify_stop()
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
        """메인 루프 1회전 동작.

        PHASE 3: 매 틱마다 HP/MP 를 확인해 임계값 이하면 포션을 사용한다.
        PHASE 6: 사냥 방식의 step() 을 1회 호출해 패턴 이동/스킬을 진행한다.
        PHASE 7: 상태 감시로 정지/반복/마을/감옥을 확인해 비정상이면 자동 정지.
        """
        try:
            macro_logic.check_and_use_potion()
            self.hunter.step()
            self._check_monitor()
            # TODO(PHASE 12): 거탐(GM) 감지 연결
        except Exception as e:
            logger.error(f"_tick 처리 실패: {e}")

    def _check_monitor(self) -> None:
        """상태 감시를 1회 수행하고, 비정상 감지 시 매크로를 자동 정지한다.

        주기(MONITOR_CHECK_INTERVAL) 가 안 됐으면 monitor 가 skipped 로
        돌려주므로 추가 처리 없이 넘어간다.
        """
        try:
            result = self.monitor.check()
            if result.get('alert'):
                reasons = ', '.join(result.get('reasons', []))
                logger.warning(f"비정상 상태 감지({reasons}) — 매크로 자동 정지")
                self.running = False
                # PHASE 8: 이상상황 알림 + 스크린샷 (논블로킹)
                telegram_bot.notify_alert(result.get('reasons', []))
        except Exception as e:
            logger.error(f"상태 감시 처리 실패: {e}")


def setup_logging() -> None:
    """로깅 기본 설정 — 코드 규칙 7: print 대신 logging 사용."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format=config.LOG_FORMAT,
    )


def verify_license() -> str:
    """시작 시 라이선스를 검증하고 현재 등급을 반환한다.

    로컬 토큰(license.dat) 또는 개발용 강제 등급으로 등급을 확정한다.
    FREE 등급이어도 기본 기능은 동작하므로 프로그램을 막지는 않고,
    등급만 확인해 로그로 안내한다. PREMIUM 전용 기능은 호출 시점에
    @require_tier 데코레이터가 개별적으로 차단한다.

    Returns:
        확정된 현재 등급 문자열 (FREE / BASIC / PREMIUM).
    """
    try:
        tier = license_manager.refresh()
        logger.info(f"라이선스 검증 완료 — 현재 등급: {tier}")
        if tier == 'FREE':
            logger.info(
                "FREE 등급으로 실행됩니다. "
                "BASIC/PREMIUM 기능은 라이선스 키 활성화가 필요합니다."
            )
        return tier
    except Exception as e:
        logger.error(f"라이선스 검증 중 오류 — FREE 로 진행: {e}")
        return 'FREE'


def main() -> None:
    """프로그램 진입점 — 로깅 설정, 라이선스 검증, 핫키 등록, 메인 루프 실행."""
    setup_logging()
    logger.info("===== 메이플 자동사냥 매크로 시작 =====")

    verify_license()

    # PHASE 8: config.json 의 텔레그램 설정 로드 (미설정이면 알림 비활성)
    telegram_bot.reload()

    app = MacroApp()
    if not app.register_hotkeys():
        logger.error("핫키 등록에 실패하여 종료합니다.")
        return

    app.run()
    logger.info("===== 프로그램 정상 종료 =====")


if __name__ == '__main__':
    main()
