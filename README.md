# KoreaLotto645 Data & Policy

이 저장소는 로또픽 6/45 안드로이드 앱을 위한 개인정보 처리방침과 로또 당첨 데이터 피드를 호스팅합니다.

## 구성 요소

### 1. 개인정보 처리방침 (Privacy Policy)
- URL: [https://taylor-song.github.io/korealotto645/korealotto645-privacy-policy.html](https://taylor-song.github.io/korealotto645/korealotto645-privacy-policy.html)

### 2. 로또 당첨 데이터 피드 (Lotto Draw Feed)
- URL: [https://taylor-song.github.io/korealotto645/data/draws_delta.json](https://taylor-song.github.io/korealotto645/data/draws_delta.json)
- **베이스라인**: 앱 내부에 1회부터 1204회까지의 데이터가 포함되어 있습니다.
- **업데이트 범위**: 이 원격 피드는 1205회부터 최신 회차까지의 데이터를 제공합니다.
- **자동화**: GitHub Actions를 통해 매주 일요일 03:00 UTC (한국 시간 12:00)에 자동으로 업데이트됩니다.

## JSON 스키마 상세

```json
{
  "schemaVersion": 1,
  "baseDrawNo": 1204,
  "updatedAt": "ISO Timestamp",
  "latestDrawNo": 1206,
  "draws": [
    {
      "drawNo": 1205,
      "drawDate": "YYYY-MM-DD",
      "numbers": [1, 2, 3, 4, 5, 6],
      "bonusNumber": 7,
      "firstWinnerCount": 10,
      "firstPrizeAmount": 1234567890,
      "totalSellAmount": 123456789000
    }
  ]
}
```

- `drawNo`: 회차 (Integer)
- `drawDate`: 추첨일 (YYYY-MM-DD)
- `numbers`: 당첨 번호 6개 (Array)
- `bonusNumber`: 보너스 번호 (Integer)
- `firstWinnerCount`: 1등 당첨자 수
- `firstPrizeAmount`: 1등 당첨 금액 (단위: 원)
- `totalSellAmount`: 총 판매 금액 (단위: 원)

## 관리 안내

데이터 업데이트 스크립트는 `scripts/update_korea_lotto.py`에 위치하며 다음의 소스를 사용합니다:
1. **공식 소스**: 동행복권 API (우선 시도)
2. **백업 소스**: [smok95/lotto](https://github.com/smok95/lotto) 공개 JSON 아카이브 (공식 소스 실패 시 사용)

모든 데이터는 수집 후 검증 및 정규화 과정을 거쳐 이 저장소의 피드([draws_delta.json](https://taylor-song.github.io/korealotto645/data/draws_delta.json))로 발행됩니다. 

**주의**: 이 피드는 안드로이드 앱의 편의를 위해 제공되는 데이터이며, 법적인 효력을 갖는 공식 당첨 결과는 반드시 [동행복권 홈페이지](https://www.dhlottery.co.kr)에서 확인하시기 바랍니다.

수동으로 업데이트를 실행하려면 GitHub Actions 탭에서 `Update Korea Lotto Data` 워크플로우를 `workflow_dispatch`로 실행하십시오.
