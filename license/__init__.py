"""라이선스 시스템 패키지.

하이브리드 방식 라이선스 검증을 담당한다.
  - hardware_id    : 하드웨어 고유 ID 생성 (CPU + MAC)
  - online_validator : 최초 1회 온라인 서버 인증 (PHASE 2 는 stub)
  - local_validator  : 이후 license.dat + 하드웨어ID 로컬 검증
  - license_manager  : 등급 확인 + @require_tier 데코레이터 (외부 진입점)
"""
