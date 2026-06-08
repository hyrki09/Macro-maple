"""상태 감시 시스템 모듈 (PHASE 7).

매크로 동작 중 비정상 상황을 감지해 메인 루프가 자동으로 정지하도록 신호를 준다.

감지 항목:
  - detect_position_stuck() : 캐릭터가 장시간 같은 자리에 머묾 (끼임/멈춤)
  - detect_position_loop()  : 좁은 좌표를 계속 반복 (벽 끼임/제자리 바운스)
  - detect_town()           : 마을 화면으로 이탈
  - detect_jail()           : 감옥 화면 진입

정지/반복은 미니맵 캐릭터 좌표(screen_capture.get_character_position)를,
마을/감옥은 화면 템플릿 매칭(screen_capture)을 사용한다.
(코드 규칙 4: OpenCV 기반, 5: 메모리 직접 읽기 금지, 6: 예외처리 필수,
 7: logging 사용)

거탐(GM) 감지는 PHASE 12 에서 별도로 추가한다.
"""

import logging
import time
from collections import Counter, deque

import config
import screen_capture

logger = logging.getLogger(__name__)


class StateMonitor:
    """캐릭터 위치/화면을 표본 추출해 비정상 상황을 판정하는 감시자.

    시간 기준은 monotonic 시계라 시스템 시간 변경에 영향받지 않는다.
    매크로 시작 시 reset() 으로 누적 상태를 비워야 한다.

    상태:
        _last_pos        : 마지막으로 '움직였다'고 본 기준 좌표
        _last_move_time  : 그 움직임이 있던 monotonic 시각
        _pos_history     : 반복 판정을 위한 최근 양자화 좌표 큐
        _last_check_time : check() 표본 추출 주기 제어용 마지막 시각
    """

    def __init__(self):
        """감시 상태를 초기 상태로 둔다."""
        self._last_pos = None
        self._last_move_time = None
        self._pos_history = deque(maxlen=config.LOOP_HISTORY_SIZE)
        self._last_check_time = None

    def reset(self) -> None:
        """누적된 감시 상태를 모두 비운다 (매크로 시작/재개 시 호출)."""
        try:
            self._last_pos = None
            self._last_move_time = None
            self._pos_history.clear()
            self._last_check_time = None
            logger.debug("상태 감시 초기화")
        except Exception as e:
            logger.error(f"상태 감시 초기화 실패: {e}")

    # ----- 정지 감지 -----

    def detect_position_stuck(self, pos: tuple | None,
                              now: float | None = None) -> bool:
        """캐릭터가 장시간 같은 자리에 머무는지 판정한다.

        현재 좌표가 직전 기준 좌표에서 STUCK_POS_TOLERANCE(px) 보다 더
        움직였으면 기준 좌표/시각을 갱신한다. 움직이지 않은 채로
        STUCK_TIME_THRESHOLD(초) 가 지나면 정지로 본다.

        Args:
            pos: 현재 캐릭터 (x, y). 읽지 못했으면 None.
            now: 현재 monotonic 시각. None 이면 time.monotonic().

        Returns:
            장시간 정지 상태면 True. 위치를 못 읽었으면(None) False.
        """
        try:
            if now is None:
                now = time.monotonic()
            # 위치를 못 읽으면 판정 불가 — 타이머도 건드리지 않는다(전이 손실 방지)
            if pos is None:
                return False

            # 첫 표본: 기준만 세우고 정지 아님
            if self._last_pos is None or self._last_move_time is None:
                self._last_pos = pos
                self._last_move_time = now
                return False

            dx = abs(pos[0] - self._last_pos[0])
            dy = abs(pos[1] - self._last_pos[1])
            moved = (dx > config.STUCK_POS_TOLERANCE or
                     dy > config.STUCK_POS_TOLERANCE)
            if moved:
                # 움직였으면 기준 갱신 후 정지 아님
                self._last_pos = pos
                self._last_move_time = now
                return False

            elapsed = now - self._last_move_time
            if elapsed >= config.STUCK_TIME_THRESHOLD:
                logger.warning(
                    f"정지 감지 — {elapsed:.0f}s 동안 위치 변화 없음 (좌표:{pos})"
                )
                return True
            return False
        except Exception as e:
            logger.error(f"정지 감지 실패: {e}")
            return False

    # ----- 반복 좌표 감지 -----

    def detect_position_loop(self, pos: tuple | None) -> bool:
        """좁은 좌표를 계속 반복하는지(끼임/제자리 바운스) 판정한다.

        좌표를 LOOP_POS_TOLERANCE(px) 격자로 양자화해 큐에 쌓고, 큐가
        가득 찼을 때 가장 자주 나온 칸의 횟수가 LOOP_REPEAT_THRESHOLD
        이상이면 반복으로 본다. 정상 좌우 스윕은 x 범위가 넓어 한 칸이
        임계 횟수만큼 차지하지 않는다.

        Args:
            pos: 현재 캐릭터 (x, y). 읽지 못했으면 None.

        Returns:
            같은 곳을 비정상적으로 반복하면 True.
        """
        try:
            if pos is None:
                return False

            tol = config.LOOP_POS_TOLERANCE
            cell = (pos[0] // tol, pos[1] // tol) if tol > 0 else pos
            self._pos_history.append(cell)

            # 큐가 가득 차기 전에는 표본이 부족해 판정하지 않는다
            if len(self._pos_history) < self._pos_history.maxlen:
                return False

            (_, count), = Counter(self._pos_history).most_common(1)
            if count >= config.LOOP_REPEAT_THRESHOLD:
                logger.warning(
                    f"반복 좌표 감지 — 최근 {self._pos_history.maxlen}표본 중 "
                    f"한 위치가 {count}회 반복"
                )
                return True
            return False
        except Exception as e:
            logger.error(f"반복 좌표 감지 실패: {e}")
            return False

    # ----- 마을/감옥 감지 (템플릿 매칭) -----

    @staticmethod
    def _match_template(template_path: str, region: dict,
                        threshold: float, label: str,
                        screen=None) -> bool:
        """주어진 템플릿이 화면 영역에 존재하는지 검사한다 (공용 헬퍼).

        Args:
            template_path: 템플릿 이미지 경로.
            region: 캡처할 화면 영역 {'x','y','w','h'}.
            threshold: 매칭 임계값(0~1).
            label: 로그에 표시할 감지 이름 (예: '마을').
            screen: 미리 캡처한 화면 이미지. None 이면 region 을 직접 캡처.

        Returns:
            템플릿을 임계값 이상으로 찾으면 True. 템플릿/캡처 실패 시 False.
        """
        try:
            template = screen_capture.load_template(template_path)
            if template is None:
                # load_template 이 안내 로그를 남긴다 — 감지 불가, 안전하게 False
                return False

            if screen is None:
                screen = screen_capture.capture_region(region)
            if screen is None:
                logger.error(f"{label} 감지 실패 — 화면 캡처 없음")
                return False

            match = screen_capture.find_template(
                screen, template, threshold=threshold
            )
            if match is not None:
                logger.warning(
                    f"{label} 감지 — 매칭 점수 {match['score']:.3f}"
                )
                return True
            return False
        except Exception as e:
            logger.error(f"{label} 감지 실패: {e}")
            return False

    def detect_town(self, screen=None) -> bool:
        """마을 화면으로 이탈했는지 판정한다 (템플릿 매칭).

        Args:
            screen: 미리 캡처한 화면. None 이면 TOWN_DETECT_REGION 캡처.

        Returns:
            마을 화면이면 True.
        """
        return self._match_template(
            config.TOWN_TEMPLATE_PATH, config.TOWN_DETECT_REGION,
            config.TOWN_MATCH_THRESHOLD, '마을', screen=screen,
        )

    def detect_jail(self, screen=None) -> bool:
        """감옥 화면에 진입했는지 판정한다 (템플릿 매칭).

        Args:
            screen: 미리 캡처한 화면. None 이면 JAIL_DETECT_REGION 캡처.

        Returns:
            감옥 화면이면 True.
        """
        return self._match_template(
            config.JAIL_TEMPLATE_PATH, config.JAIL_DETECT_REGION,
            config.JAIL_MATCH_THRESHOLD, '감옥', screen=screen,
        )

    # ----- 통합 점검 -----

    def check(self, now: float | None = None) -> dict:
        """모든 감지를 1회 수행하고 종합 결과를 반환한다.

        MONITOR_CHECK_INTERVAL 주기로만 실제 표본 추출을 하며, 주기가
        안 됐으면 표본 없이 skipped 결과를 돌려준다(불필요한 캡처 방지).
        하나라도 비정상이면 alert=True 와 사유 목록을 채운다.

        Args:
            now: 현재 monotonic 시각. None 이면 time.monotonic().

        Returns:
            결과 딕셔너리:
                {'alert': bool, 'reasons': list[str], 'pos': tuple|None,
                 'stuck': bool, 'loop': bool, 'town': bool, 'jail': bool,
                 'skipped': bool}
        """
        result = {
            'alert': False, 'reasons': [], 'pos': None,
            'stuck': False, 'loop': False, 'town': False, 'jail': False,
            'skipped': False,
        }
        try:
            if now is None:
                now = time.monotonic()

            # 표본 추출 주기 제어 — 너무 잦은 캡처/반복판정 왜곡 방지
            if (self._last_check_time is not None and
                    now - self._last_check_time < config.MONITOR_CHECK_INTERVAL):
                result['skipped'] = True
                return result
            self._last_check_time = now

            pos = screen_capture.get_character_position()
            result['pos'] = pos

            result['stuck'] = self.detect_position_stuck(pos, now=now)
            result['loop'] = self.detect_position_loop(pos)
            result['town'] = self.detect_town()
            result['jail'] = self.detect_jail()

            for name in ('stuck', 'loop', 'town', 'jail'):
                if result[name]:
                    result['reasons'].append(name)
            result['alert'] = bool(result['reasons'])
            return result
        except Exception as e:
            logger.error(f"상태 감시 점검 실패: {e}")
            return result


# 프로그램 전역에서 공유하는 싱글톤 — 메인 루프에서 매 틱 호출한다
state_monitor = StateMonitor()


def check() -> dict:
    """전역 state_monitor.check 의 단축 래퍼.

    Returns:
        check 결과 딕셔너리.
    """
    return state_monitor.check()


def reset() -> None:
    """전역 state_monitor.reset 의 단축 래퍼 (매크로 시작 시 호출)."""
    state_monitor.reset()
