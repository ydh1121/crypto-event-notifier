import {getJson} from '../core/http.js';

export async function getStrategyJournal(exchange, market, experiment, {revision='',offset=0,limit=30}={}) {
  const query = new URLSearchParams({exchange,market,strategy:'adaptive',experiment,revision,offset:String(offset),limit:String(limit)});
  const body = await getJson(`/api/market-detail?${query}`);
  if(body.exchange!==exchange || body.market!==market || body.journal?.account?.experiment_id!==experiment) {
    throw new Error('선택한 코인의 체결 내역을 확인하지 못했습니다.');
  }
  return body.journal;
}
