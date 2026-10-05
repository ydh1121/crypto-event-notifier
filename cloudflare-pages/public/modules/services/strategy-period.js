import {getJson} from '../core/http.js';

export async function getStrategyPeriod(scope, selection) {
  const body=await getJson(`/api/strategy-period?${new URLSearchParams({...scope,...selection})}`);
  const review=body.review;
  if(!review||review.exchange!==scope.exchange||review.market!==scope.market
      ||(review.status==='ok'&&review.period!==selection.period)) {
    throw new Error('선택한 코인의 기간별 매매 기록을 확인하지 못했습니다.');
  }
  return review;
}
