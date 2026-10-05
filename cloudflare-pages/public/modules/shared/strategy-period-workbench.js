import {getStrategyPeriod} from '../services/strategy-period.js';
import {strategyPeriodHtml} from './strategy-period-view.js';
import {createScopedReview} from './scoped-review.js';

export function createStrategyPeriod({openJournal}) {
  return createScopedReview({
    scopeKey:s=>`${s.exchange}|${s.market}`,
    defaults:s=>({period:'30d',style:s.style||'aggressive'}),
    fetchReview:getStrategyPeriod, renderHtml:strategyPeriodHtml, placeholder:'기간별 매매를 불러오는 중…',
    receive:(selection,result)=>{selection.experiment=result.selected_experiment||'';},
    action(button,selection){
      if(button.dataset.periodJournal){openJournal(button.dataset.periodJournal);return false;}
      if(button.dataset.periodRange)selection.period=button.dataset.periodRange;
      else if(button.dataset.periodExperiment)selection.experiment=button.dataset.periodExperiment;
      else if(!button.hasAttribute('data-period-retry'))return false;
      return true;
    },
  });
}
