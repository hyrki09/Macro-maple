"""PHASE 8 텔레그램 알림 테스트 스크립트.

실제 네트워크/게임/화면 없이 헤드리스로 검증한다.

  python test_phase8.py

검증 항목
  1) load_telegram_config — 파일 없음/정상/손상 시 기본값·로드 동작
  2) is_configured       — 비활성/토큰누락/완비 상태 판정
  3) send_message        — 미설정 시 무전송, 설정 시 sendMessage 호출/데이터
  4) send_screenshot     — sendPhoto 호출, 캡처 실패 시 텍스트 폴백
  5) notify_alert        — 사유 리스트 포맷 + 스크린샷 경로
  6) async 래퍼          — 백그라운드 전송 완료, 미설정 시 무전송
  7) main 연동           — 시작/중지/이상상황에 알림 호출
"""

import json
import logging
import os
import sys
import tempfile
import threading

# 콘솔 인코딩 문제(cp949) 방지 — stdout/stderr UTF-8 재설정
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import config
import telegram_bot

logging.basicConfig(level=logging.ERROR, format='  %(levelname)s: %(message)s')

_passed = 0
_failed = 0


def check(name: str, condition: bool) -> None:
    """단일 검사 결과를 출력하고 카운터를 갱신한다."""
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}")


def make_notifier(enabled=True, token='T', chat_id='C'):
    """테스트용 TelegramNotifier 를 만들어 상태를 직접 주입한다.

    config.json 로드 결과에 의존하지 않도록 reload 후 값을 덮어쓴다.
    requests 가 없는 환경에서도 is_configured 가 통과하도록 가용 플래그를 켠다.
    """
    n = telegram_bot.TelegramNotifier()
    n.enabled = enabled
    n.token = token
    n.chat_id = chat_id
    return n


def test_load_config() -> None:
    """load_telegram_config 파일 처리 검증."""
    print("\n[1] load_telegram_config")

    # (a) 파일 없음 → 기본값(비활성)
    cfg = telegram_bot.load_telegram_config('___no_such_file___.json')
    check("파일 없으면 기본값", cfg == config.TELEGRAM_DEFAULTS and cfg['enabled'] is False)

    # (b) 정상 파일 → telegram 블록 로드
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'config.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'telegram': {'enabled': True, 'token': 'TK',
                                    'chat_id': '123'}}, f)
        cfg = telegram_bot.load_telegram_config(p)
        check("정상 파일 로드", cfg['enabled'] is True and cfg['token'] == 'TK'
              and cfg['chat_id'] == '123')

        # (c) telegram 블록 없음 → 기본값
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'other': 1}, f)
        cfg = telegram_bot.load_telegram_config(p)
        check("블록 없으면 기본값", cfg == config.TELEGRAM_DEFAULTS)

        # (d) 손상 JSON → 기본값(예외 안전)
        with open(p, 'w', encoding='utf-8') as f:
            f.write('{ broken json')
        cfg = telegram_bot.load_telegram_config(p)
        check("손상 JSON 이면 기본값", cfg == config.TELEGRAM_DEFAULTS)


def test_is_configured() -> None:
    """is_configured 상태 판정 검증."""
    print("\n[2] is_configured")
    # requests 가용 여부에 의존하므로 강제로 켜고 검증
    orig = telegram_bot._REQUESTS_AVAILABLE
    telegram_bot._REQUESTS_AVAILABLE = True
    try:
        check("완비 → True", make_notifier().is_configured() is True)
        check("비활성 → False", make_notifier(enabled=False).is_configured() is False)
        check("토큰 누락 → False", make_notifier(token='').is_configured() is False)
        check("채팅ID 누락 → False", make_notifier(chat_id='').is_configured() is False)

        telegram_bot._REQUESTS_AVAILABLE = False
        check("requests 없으면 False", make_notifier().is_configured() is False)
    finally:
        telegram_bot._REQUESTS_AVAILABLE = orig


def test_send_message() -> None:
    """send_message 전송/미전송 검증."""
    print("\n[3] send_message")
    orig = telegram_bot._REQUESTS_AVAILABLE
    telegram_bot._REQUESTS_AVAILABLE = True
    try:
        calls = []

        # (a) 설정 완비 → sendMessage 호출, 올바른 데이터, True
        n = make_notifier()
        n._api_request = lambda method, data, files=None: (
            calls.append((method, data, files)) or True)
        ok = n.send_message('hi')
        check("설정 시 전송 성공", ok is True)
        check("sendMessage 호출", calls and calls[0][0] == 'sendMessage')
        check("데이터에 chat_id/text",
              calls[0][1].get('chat_id') == 'C' and calls[0][1].get('text') == 'hi')

        # (b) 미설정(비활성) → 전송 안 함, False
        calls.clear()
        n2 = make_notifier(enabled=False)
        n2._api_request = lambda *a, **k: calls.append('X') or True
        ok2 = n2.send_message('hi')
        check("미설정 시 무전송 + False", ok2 is False and not calls)

        # (c) API 실패 → False
        n3 = make_notifier()
        n3._api_request = lambda *a, **k: False
        check("API 실패 시 False", n3.send_message('hi') is False)
    finally:
        telegram_bot._REQUESTS_AVAILABLE = orig


def test_send_screenshot() -> None:
    """send_screenshot 사진 전송 및 폴백 검증."""
    print("\n[4] send_screenshot")
    orig = telegram_bot._REQUESTS_AVAILABLE
    telegram_bot._REQUESTS_AVAILABLE = True
    try:
        calls = []

        # (a) 캡처 성공 → sendPhoto + files + caption
        n = make_notifier()
        n._capture_png = staticmethod(lambda: b'PNGBYTES')
        n._api_request = lambda method, data, files=None: (
            calls.append((method, data, files)) or True)
        ok = n.send_screenshot('caption!')
        check("스크린샷 전송 성공", ok is True)
        check("sendPhoto 호출", calls and calls[0][0] == 'sendPhoto')
        check("files 에 photo 포함", 'photo' in (calls[0][2] or {}))
        check("caption 전달", calls[0][1].get('caption') == 'caption!')

        # (b) 캡처 실패 → 텍스트 폴백(sendMessage)
        calls.clear()
        n2 = make_notifier()
        n2._capture_png = staticmethod(lambda: None)
        n2._api_request = lambda method, data, files=None: (
            calls.append((method, data, files)) or True)
        ok2 = n2.send_screenshot('fallback')
        check("캡처 실패 시 텍스트 폴백", ok2 is True and calls
              and calls[0][0] == 'sendMessage')

        # (c) 미설정 → 무전송
        calls.clear()
        n3 = make_notifier(enabled=False)
        n3._api_request = lambda *a, **k: calls.append('X') or True
        check("미설정 시 스크린샷 무전송", n3.send_screenshot('x') is False and not calls)
    finally:
        telegram_bot._REQUESTS_AVAILABLE = orig


def test_notify_alert() -> None:
    """notify_alert 사유 포맷 + 스크린샷 전송 검증."""
    print("\n[5] notify_alert")
    orig = telegram_bot._REQUESTS_AVAILABLE
    telegram_bot._REQUESTS_AVAILABLE = True
    try:
        captured = {}

        # 전역 notifier 를 활성 상태로 만들고 send_screenshot 가로채기
        telegram_bot.notifier.enabled = True
        telegram_bot.notifier.token = 'T'
        telegram_bot.notifier.chat_id = 'C'

        done = threading.Event()

        def fake_send(caption=None):
            captured['caption'] = caption
            done.set()
            return True
        telegram_bot.notifier.send_screenshot = fake_send

        telegram_bot.notify_alert(['town', 'jail'])
        done.wait(timeout=2.0)
        check("이상상황 시 스크린샷 전송", done.is_set())
        check("사유 리스트 포맷",
              captured.get('caption') == config.MSG_MACRO_ALERT.format(reasons='town, jail'))
    finally:
        telegram_bot._REQUESTS_AVAILABLE = orig
        # 가로챈 메서드 원복
        telegram_bot.notifier = telegram_bot.TelegramNotifier()


def test_async() -> None:
    """async 래퍼가 백그라운드로 전송하고, 미설정 시 무전송함을 검증."""
    print("\n[6] async 래퍼")
    orig = telegram_bot._REQUESTS_AVAILABLE
    telegram_bot._REQUESTS_AVAILABLE = True
    try:
        # (a) 설정 완비 → 백그라운드 전송 완료
        n = make_notifier()
        done = threading.Event()
        sent = []

        def rec(method, data, files=None):
            sent.append(method)
            done.set()
            return True
        n._api_request = rec
        n.send_message_async('bg')
        done.wait(timeout=2.0)
        check("백그라운드 전송 완료", done.is_set() and sent == ['sendMessage'])

        # (b) 미설정 → 스레드 생성/전송 없음
        n2 = make_notifier(enabled=False)
        flag = []
        n2._api_request = lambda *a, **k: flag.append('X') or True
        n2.send_message_async('bg')
        check("미설정 시 무전송", not flag)
    finally:
        telegram_bot._REQUESTS_AVAILABLE = orig


def test_main_integration() -> None:
    """main 의 toggle/_check_monitor 가 알림을 호출하는지 검증."""
    print("\n[7] main 연동")
    import main

    events = []
    orig = {
        'start': telegram_bot.notify_start,
        'stop': telegram_bot.notify_stop,
        'alert': telegram_bot.notify_alert,
    }
    telegram_bot.notify_start = lambda: events.append('start')
    telegram_bot.notify_stop = lambda: events.append('stop')
    telegram_bot.notify_alert = lambda reasons: events.append(('alert', reasons))
    try:
        app = main.MacroApp.__new__(main.MacroApp)  # __init__ 우회
        app.running = False

        class FakeMonitor:
            def reset(self):
                pass

            def check(self):
                return {'alert': True, 'reasons': ['town'], 'pos': None,
                        'stuck': False, 'loop': False, 'town': True,
                        'jail': False, 'skipped': False}
        app.monitor = FakeMonitor()

        # 시작 토글 → start 알림
        app.toggle()
        check("시작 시 start 알림", app.running is True and 'start' in events)

        # 중지 토글 → stop 알림
        app.toggle()
        check("중지 시 stop 알림", app.running is False and 'stop' in events)

        # 이상상황 감지 → alert 알림 + 정지
        app.running = True
        app._check_monitor()
        check("이상상황 시 alert 알림",
              app.running is False
              and any(isinstance(e, tuple) and e[0] == 'alert' for e in events))
    finally:
        telegram_bot.notify_start = orig['start']
        telegram_bot.notify_stop = orig['stop']
        telegram_bot.notify_alert = orig['alert']


def main() -> None:
    """헤드리스 자동 검증 실행."""
    print("===== PHASE 8 텔레그램 알림 테스트 =====")
    test_load_config()
    test_is_configured()
    test_send_message()
    test_send_screenshot()
    test_notify_alert()
    test_async()
    test_main_integration()
    print(f"\n===== 결과: {_passed} 통과 / {_failed} 실패 =====")
    sys.exit(_failed)


if __name__ == '__main__':
    main()
