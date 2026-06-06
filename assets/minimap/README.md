# assets/minimap/

미니맵 좌표 인식(PHASE 5)에 쓰는 템플릿 이미지를 두는 폴더.

## char_dot.png (필수)

미니맵에서 **캐릭터 위치를 나타내는 점/화살표**만 잘라낸 작은 PNG.

### 만드는 법
1. 빨간 코끼리 2 맵에 입장해 미니맵이 보이는 상태로 전체화면 캡처.
2. 미니맵에서 내 캐릭터 점(보통 노란/흰색 점)만 사각형으로 잘라낸다.
   - 배경(미니맵 지형)이 최대한 안 들어가게, 점에 딱 맞게 자른다.
   - 점이 너무 작으면 주변 1~2px 여유만 둔다.
3. `assets/minimap/char_dot.png` 로 저장.

### 주의
- **반드시 실제 게임에서 직접 캡처** — 인터넷 이미지 X (해상도/색감이 달라 매칭 실패).
- 모든 좌표는 1920x1080 전체화면 기준. 해상도가 다르면
  `config.MINIMAP_REGION` 도 함께 보정해야 한다.
- 템플릿이 없으면 `get_character_position()` 은 안내 로그를 남기고 `None` 을 반환한다.

### 보정
- 매칭이 안 되면 `config.MINIMAP_MATCH_THRESHOLD` 를 0.6 까지 낮추고
  `get_character_position(debug=True)` 로 `max_val` 로그를 보며 임계값을 조정한다.
- 라이브 확인: `python test_phase5.py --live`
