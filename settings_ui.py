"""설정 UI 모듈 (PHASE 10).

tkinter 로 설정 창을 띄워 사용자가 config.json 값을 보고 수정/저장한다.

표시/편집 항목
  - 라이선스 키 입력 + 현재 등급 표시 (활성화 버튼)
  - 사냥 방식 (패턴 / YOLO)   — YOLO 는 PREMIUM 전용
  - 맵 선택   (빨코2 / 미니던전) — FREE 는 1개 고정, BASIC+ 전체
  - 모드 선택 (저스펙 / 고스펙)  — 고스펙은 PREMIUM 전용
  - 소모품 구매 수량 / 상점 주기 / 펫먹이 주기 / 텔레포트 주기
  - 텔레그램 토큰 / 채팅ID + 알림 사용 여부

등급 게이팅과 값 구성 로직은 Tk 없이도 검증할 수 있도록 순수 함수로 분리했다.
저장 시 등급으로 허용되지 않는 선택은 안전한 기본값으로 강등(enforce)해
하위 등급이 상위 기능을 저장하지 못하게 한다.

(코드 규칙 1: 한국어 docstring, 3: 설정은 config 에서, 6: 예외처리, 7: logging)
"""

import logging

import config
import shop_routine
import telegram_bot
import user_config
from license.license_manager import TIER_LEVELS, license_manager

logger = logging.getLogger(__name__)

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
    _TK_AVAILABLE = True
except Exception as e:  # 디스플레이/Tk 없는 환경에서도 임포트는 되게 한다
    tk = None
    ttk = None
    messagebox = None
    _TK_AVAILABLE = False
    logger.debug(f"tkinter 임포트 실패 — 설정 창 비활성화: {e}")


# ===== 순수 로직 (Tk 비의존, 테스트 가능) =====

def _tier_at_least(tier: str, required: str) -> bool:
    """tier 등급이 required 이상인지 비교한다."""
    return TIER_LEVELS.get(tier, 0) >= TIER_LEVELS.get(required, 999)


def allowed_hunt_modes(tier: str) -> list:
    """등급에서 선택 가능한 사냥 방식 목록을 반환한다 (YOLO 는 PREMIUM)."""
    modes = [config.HUNT_MODE_PATTERN]
    if _tier_at_least(tier, 'PREMIUM'):
        modes.append(config.HUNT_MODE_YOLO)
    return modes


def allowed_maps(tier: str) -> list:
    """등급에서 선택 가능한 맵 목록을 반환한다 (FREE 는 1개 고정)."""
    if _tier_at_least(tier, 'BASIC'):
        return [config.MAP_RED_ELEPHANT2, config.MAP_RED_ELEPHANT2_MINI]
    return [config.MAP_DEFAULT]


def allowed_skill_modes(tier: str) -> list:
    """등급에서 선택 가능한 스킬 모드 목록을 반환한다 (고스펙은 PREMIUM)."""
    modes = [config.SKILL_MODE_LOWSPEC]
    if _tier_at_least(tier, 'PREMIUM'):
        modes.append(config.SKILL_MODE_HIGHSPEC)
    return modes


def to_int(value, default: int) -> int:
    """값을 정수로 안전하게 변환한다. 실패 시 default 를 반환한다.

    Args:
        value: 변환할 값 (문자열/숫자 등).
        default: 변환 실패 시 사용할 기본값.

    Returns:
        변환된 정수(0 미만이면 0). 실패 시 default.
    """
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def enforce_tier_permissions(cfg: dict, tier: str) -> dict:
    """등급으로 허용되지 않는 선택을 안전한 기본값으로 강등한 새 설정을 반환한다.

    하위 등급이 상위 전용 기능(YOLO/전체 맵/고스펙)을 저장하지 못하게 막는다.

    Args:
        cfg: 검사할 설정 딕셔너리.
        tier: 현재 등급 (FREE / BASIC / PREMIUM).

    Returns:
        강등이 반영된 새 설정 딕셔너리(원본은 변경하지 않음).
    """
    result = dict(cfg)
    try:
        if result.get('hunt_mode') not in allowed_hunt_modes(tier):
            result['hunt_mode'] = config.HUNT_MODE_DEFAULT
        if result.get('map') not in allowed_maps(tier):
            result['map'] = config.MAP_DEFAULT
        if result.get('skill_mode') not in allowed_skill_modes(tier):
            result['skill_mode'] = config.SKILL_MODE_LOWSPEC
    except Exception as e:
        logger.error(f"등급 권한 강등 처리 실패: {e}")
    return result


def build_config(values: dict, base: dict, tier: str) -> dict:
    """UI 입력값(flat)을 base 설정에 반영한 저장용 전체 설정을 구성한다.

    숫자 필드는 정수로 변환하고, 등급 게이팅(enforce_tier_permissions)을 적용한다.

    Args:
        values: UI 위젯에서 모은 평면 값 딕셔너리.
            (license_key, hunt_mode, map, skill_mode, buy_quantity,
             shop_interval, pet_feed_interval, teleport_interval,
             telegram_enabled, telegram_token, telegram_chat_id, shop_enabled)
        base: 병합 기준이 되는 기존 전체 설정(load_config 결과).
        tier: 현재 등급 — 게이팅에 사용.

    Returns:
        config.json 에 저장할 전체 설정 딕셔너리.
    """
    cfg = dict(base)
    try:
        d = config.USER_CONFIG_DEFAULTS
        cfg['license_key'] = str(values.get('license_key', cfg.get('license_key', '')))
        cfg['hunt_mode'] = values.get('hunt_mode', cfg.get('hunt_mode'))
        cfg['map'] = values.get('map', cfg.get('map'))
        cfg['skill_mode'] = values.get('skill_mode', cfg.get('skill_mode'))
        cfg['pet_feed_interval'] = to_int(
            values.get('pet_feed_interval'), d['pet_feed_interval'])
        cfg['teleport_interval'] = to_int(
            values.get('teleport_interval'), d['teleport_interval'])

        # telegram 블록
        tg = dict(cfg.get(config.TELEGRAM_CONFIG_KEY, config.TELEGRAM_DEFAULTS))
        tg['enabled'] = bool(values.get('telegram_enabled', tg.get('enabled', False)))
        tg['token'] = str(values.get('telegram_token', tg.get('token', '')))
        tg['chat_id'] = str(values.get('telegram_chat_id', tg.get('chat_id', '')))
        cfg[config.TELEGRAM_CONFIG_KEY] = tg

        # shop 블록
        sh = dict(cfg.get(config.SHOP_CONFIG_KEY, config.SHOP_DEFAULTS))
        sh['enabled'] = bool(values.get('shop_enabled', sh.get('enabled', True)))
        sh['interval_sec'] = to_int(
            values.get('shop_interval'), int(config.SHOP_DEFAULTS['interval_sec']))
        sh['buy_quantity'] = to_int(
            values.get('buy_quantity'), int(config.SHOP_DEFAULTS['buy_quantity']))
        cfg[config.SHOP_CONFIG_KEY] = sh

        return enforce_tier_permissions(cfg, tier)
    except Exception as e:
        logger.error(f"설정 구성 실패: {e}")
        return enforce_tier_permissions(cfg, tier)


# ===== Tk 설정 창 =====

class SettingsUI:
    """tkinter 설정 창. 위젯에서 값을 모아 user_config 로 저장한다.

    순수 로직(build_config/enforce/allowed_*)을 위젯에 얹기만 하는 얇은 층이다.
    """

    def __init__(self, path: str | None = None):
        """설정을 로드하고 창 상태를 준비한다 (창은 show() 에서 생성)."""
        self.path = path
        self.cfg = user_config.load_config(path)
        self.tier = license_manager.get_tier()
        self.root = None
        self.vars = {}

    def _combo_values(self, ids: list, labels: dict) -> list:
        """식별자 목록을 사람이 읽는 라벨 목록으로 바꾼다(콤보박스 표시용)."""
        return [labels.get(i, i) for i in ids]

    def show(self) -> None:
        """설정 창을 띄운다. Tk 가 없으면 안내 로그만 남기고 반환한다."""
        try:
            if not _TK_AVAILABLE:
                logger.error("tkinter 가 없어 설정 창을 열 수 없습니다.")
                return
            self.root = tk.Tk()
            self.root.title("메이플 자동사냥 매크로 — 설정")
            self.root.resizable(False, False)
            self._build_widgets()
            self.root.mainloop()
        except Exception as e:
            logger.error(f"설정 창 표시 실패: {e}")

    def _build_widgets(self) -> None:
        """모든 입력 위젯을 배치하고 현재 설정값으로 초기화한다."""
        tg = self.cfg.get(config.TELEGRAM_CONFIG_KEY, config.TELEGRAM_DEFAULTS)
        sh = self.cfg.get(config.SHOP_CONFIG_KEY, config.SHOP_DEFAULTS)
        pad = {'padx': 8, 'pady': 4}
        row = 0
        frm = ttk.Frame(self.root, padding=12)
        frm.grid(row=0, column=0, sticky='nsew')

        # --- 라이선스 ---
        ttk.Label(frm, text="라이선스 키").grid(row=row, column=0, sticky='w', **pad)
        self.vars['license_key'] = tk.StringVar(value=self.cfg.get('license_key', ''))
        ttk.Entry(frm, textvariable=self.vars['license_key'], width=34).grid(
            row=row, column=1, **pad)
        ttk.Button(frm, text="활성화", command=self._on_activate).grid(
            row=row, column=2, **pad)
        row += 1
        self.tier_label = ttk.Label(frm, text=f"현재 등급: {self.tier}")
        self.tier_label.grid(row=row, column=1, sticky='w', **pad)
        row += 1

        # --- 사냥 방식 / 맵 / 모드 (등급별 허용 항목만 콤보에 노출) ---
        row = self._add_combo(frm, row, '사냥 방식', 'hunt_mode',
                              allowed_hunt_modes(self.tier), config.HUNT_MODE_LABELS,
                              self.cfg.get('hunt_mode'))
        row = self._add_combo(frm, row, '맵 선택', 'map',
                              allowed_maps(self.tier), config.MAP_LABELS,
                              self.cfg.get('map'))
        row = self._add_combo(frm, row, '모드 선택', 'skill_mode',
                              allowed_skill_modes(self.tier), config.SKILL_MODE_LABELS,
                              self.cfg.get('skill_mode'))

        # --- 숫자 설정 ---
        row = self._add_entry(frm, row, '소모품 구매 수량', 'buy_quantity',
                              sh.get('buy_quantity'))
        row = self._add_entry(frm, row, '상점 주기(초)', 'shop_interval',
                              int(sh.get('interval_sec', config.SHOP_INTERVAL)))
        row = self._add_entry(frm, row, '펫먹이 주기(초)', 'pet_feed_interval',
                              self.cfg.get('pet_feed_interval'))
        row = self._add_entry(frm, row, '텔레포트 주기(초)', 'teleport_interval',
                              self.cfg.get('teleport_interval'))

        # --- 텔레그램 ---
        self.vars['telegram_enabled'] = tk.BooleanVar(value=bool(tg.get('enabled')))
        ttk.Checkbutton(frm, text="텔레그램 알림 사용",
                        variable=self.vars['telegram_enabled']).grid(
            row=row, column=1, sticky='w', **pad)
        row += 1
        row = self._add_entry(frm, row, '텔레그램 토큰', 'telegram_token',
                              tg.get('token', ''))
        row = self._add_entry(frm, row, '텔레그램 채팅ID', 'telegram_chat_id',
                              tg.get('chat_id', ''))

        # --- 매매 사용 + 저장 ---
        self.vars['shop_enabled'] = tk.BooleanVar(value=bool(sh.get('enabled', True)))
        ttk.Checkbutton(frm, text="매매 루틴 사용 (PREMIUM)",
                        variable=self.vars['shop_enabled']).grid(
            row=row, column=1, sticky='w', **pad)
        row += 1
        ttk.Button(frm, text="저장", command=self._on_save).grid(
            row=row, column=1, sticky='e', **pad)
        ttk.Button(frm, text="닫기", command=self.root.destroy).grid(
            row=row, column=2, **pad)

    def _add_combo(self, frm, row, label, key, ids, labels, current) -> int:
        """라벨+콤보박스 한 줄을 추가하고 식별자↔라벨 매핑을 보관한다."""
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky='w', padx=8, pady=4)
        display = self._combo_values(ids, labels)
        var = tk.StringVar()
        # 현재 값이 허용 목록에 없으면 첫 항목으로
        cur_id = current if current in ids else (ids[0] if ids else '')
        var.set(labels.get(cur_id, cur_id))
        self.vars[key] = (var, ids, labels)   # 저장 시 라벨→식별자 역변환에 사용
        ttk.Combobox(frm, textvariable=var, values=display, state='readonly',
                     width=28).grid(row=row, column=1, sticky='w', padx=8, pady=4)
        return row + 1

    def _add_entry(self, frm, row, label, key, current) -> int:
        """라벨+입력칸 한 줄을 추가한다."""
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky='w', padx=8, pady=4)
        var = tk.StringVar(value='' if current is None else str(current))
        self.vars[key] = var
        ttk.Entry(frm, textvariable=var, width=34).grid(
            row=row, column=1, sticky='w', padx=8, pady=4)
        return row + 1

    def _collect(self) -> dict:
        """위젯 변수들에서 평면 값 딕셔너리를 모은다 (라벨→식별자 역변환 포함)."""
        values = {}
        for key, var in self.vars.items():
            if isinstance(var, tuple):
                # 콤보박스: (StringVar, ids, labels) — 표시 라벨을 식별자로 되돌린다
                strvar, ids, labels = var
                shown = strvar.get()
                rev = {labels.get(i, i): i for i in ids}
                values[key] = rev.get(shown, ids[0] if ids else '')
            else:
                values[key] = var.get()
        return values

    def _on_activate(self) -> None:
        """라이선스 키로 활성화를 시도하고 등급 표시를 갱신한다."""
        try:
            key = self.vars['license_key'].get().strip()
            if not key:
                messagebox.showwarning("라이선스", "라이선스 키를 입력하세요.")
                return
            ok = license_manager.activate(key)
            self.tier = license_manager.get_tier()
            self.tier_label.config(text=f"현재 등급: {self.tier}")
            if ok:
                messagebox.showinfo("라이선스", f"활성화 완료 — 등급: {self.tier}")
            else:
                messagebox.showerror("라이선스", "활성화에 실패했습니다. 키를 확인하세요.")
        except Exception as e:
            logger.error(f"라이선스 활성화 처리 실패: {e}")

    def _on_save(self) -> None:
        """현재 위젯 값을 config.json 에 저장하고 관련 모듈에 반영한다."""
        try:
            values = self._collect()
            new_cfg = build_config(values, self.cfg, self.tier)
            if user_config.save_config(new_cfg, self.path):
                self.cfg = new_cfg
                # 실행 중 모듈에 즉시 반영 (같은 프로세스일 때)
                telegram_bot.reload(self.path)
                shop_routine.reload(self.path)
                messagebox.showinfo("설정", "설정을 저장했습니다.")
            else:
                messagebox.showerror("설정", "설정 저장에 실패했습니다.")
        except Exception as e:
            logger.error(f"설정 저장 처리 실패: {e}")


def open_settings(path: str | None = None) -> None:
    """설정 창을 띄우는 진입 함수."""
    SettingsUI(path).show()


if __name__ == '__main__':
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format=config.LOG_FORMAT,
    )
    open_settings()
