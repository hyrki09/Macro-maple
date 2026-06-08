# assets/map_markers/

상태 감시(PHASE 7)에서 마을/감옥 이탈을 감지할 때 쓰는 템플릿 이미지 폴더.

## town.png (마을 감지)

**마을 화면에서만 보이는 UI 요소**만 잘라낸 PNG.
(예: 마을 상점/포탈/특정 NPC, 마을 전용 미니맵 마커 등 — 사냥 맵에는 없는 것)

## jail.png (감옥 감지)

**감옥(블락 처리) 화면에서만 보이는 UI 요소**만 잘라낸 PNG.

### 만드는 법
1. 해당 상황(마을 진입 / 감옥)에서 1920x1080 전체화면 캡처.
2. 그 화면에만 고유하게 나타나는 부분을 사각형으로 잘라낸다.
   - 사냥 맵에도 있는 공통 UI(HP/MP바 등)는 피한다 — 오탐 원인.
3. 각각 `assets/map_markers/town.png`, `assets/map_markers/jail.png` 로 저장.

### 주의
- **반드시 실제 게임에서 직접 캡처** — 인터넷 이미지 X (해상도/색감이 달라 매칭 실패).
- 모든 좌표는 1920x1080 전체화면 기준.
- 템플릿이 없으면 `detect_town()` / `detect_jail()` 은 안내 로그를 남기고
  안전하게 `False` 를 반환한다(매크로를 막지 않음).

### 보정
- 오탐이 잦으면 `config.TOWN_MATCH_THRESHOLD` / `JAIL_MATCH_THRESHOLD` 를 올린다(예: 0.85).
- 감지가 안 되면 0.70 까지 낮추고 매칭 점수 로그를 보며 조정한다.
- 특정 UI 위치로 `config.TOWN_DETECT_REGION` / `JAIL_DETECT_REGION` 을
  좁히면 오탐을 더 줄일 수 있다(기본값은 전체 화면).
