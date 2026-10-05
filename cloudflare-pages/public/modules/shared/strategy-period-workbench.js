import {getStrategyPeriod} from '../services/strategy-period.js';
import {strategyPeriodHtml} from './strategy-period-view.js';
import {createScopedReview} from './scoped-review.js';

export function createStrategyPeriod({openJournal,chooseStrategy=null,changed}) {
  return createScopedReview({
    scopeKey:s=>`${s.exchange}|${s.market}`,
    defaults:s=>({period:'30d',style:s.style||'aggressive'}),
    fetchReview:getStrategyPeriod, changed,
    renderHtml:(review,selection,state)=>strategyPeriodHtml(review,selection,{...state,canChoose:Boolean(chooseStrategy)}),
    placeholder:'기간별 매매를 불러오는 중…',
    receive:(selection,result)=>{selection.experiment=result.selected_experiment||'';},
    action(button,selection,review){
      if(button.dataset.periodJournal){openJournal(button.dataset.periodJournal,review);return false;}
      if(button.dataset.periodUse){
        if(review?.strategies?.some(r=>r.experiment_id===button.dataset.periodUse&&r.status==='ok'))chooseStrategy?.(button.dataset.periodUse,review);
        return false;
      }
      if(button.dataset.periodRange)selection.period=button.dataset.periodRange;
      else if(button.dataset.periodExperiment)selection.experiment=button.dataset.periodExperiment;
      else if(!button.hasAttribute('data-period-retry'))return false;
      return true;
    },
  });
}
