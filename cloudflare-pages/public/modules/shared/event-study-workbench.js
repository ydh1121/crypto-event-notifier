import {getEventStudy} from '../services/event-study.js';
import {eventStudyHtml} from './event-study-view.js';
import {createScopedReview} from './scoped-review.js';

export function createEventStudy({openJournal}) {
  return createScopedReview({
    scopeKey:s=>`${s.exchange}|${s.market}|${s.category}`,
    defaults:s=>({horizon:'15m',style:s.style||'aggressive'}),
    fetchReview:getEventStudy, renderHtml:eventStudyHtml, placeholder:'누적 기록을 불러오는 중…',
    receive:(selection,result)=>Object.assign(selection,result.selected||{},{experiment:result.selected_experiment||''}),
    action(button,selection){
      if(button.dataset.studyJournal){openJournal(button.dataset.studyJournal);return false;}
      if(button.dataset.studyHorizon)selection.horizon=button.dataset.studyHorizon;
      else if(button.dataset.studyType)Object.assign(selection,{source_id:button.dataset.studySource,event_type:button.dataset.studyType});
      else if(button.dataset.studyExperiment)selection.experiment=button.dataset.studyExperiment;
      else if(!button.hasAttribute('data-study-retry'))return false;
      return true;
    },
  });
}
