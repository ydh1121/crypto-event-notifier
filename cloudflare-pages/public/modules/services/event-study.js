import {getJson} from '../core/http.js';

export async function getEventStudy(scope, selection) {
  const body=await getJson(`/api/event-study?${new URLSearchParams({...scope,...selection})}`);
  const study=body.study;
  if(!study||study.exchange!==scope.exchange||study.market!==scope.market
      ||(study.status==='ok'&&(study.category!==scope.category||study.horizon!==selection.horizon))) {
    throw new Error('선택한 코인의 누적 기록을 확인하지 못했습니다.');
  }
  return study;
}
