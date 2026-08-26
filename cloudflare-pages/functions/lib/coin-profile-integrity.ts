import type {ExchangeMarketName} from './exchange-market-names';

export type ProfileIntegrityRow = {
  exchange:string;
  market:string;
  korean_name:string;
  english_name:string;
  provider:string;
  provider_id:string;
  business_summary_ko:string;
  description_ko:string;
  description_en:string;
  homepage:string;
  evidence_json:string;
  research_status:string;
  source_count:number;
  match_confidence:number;
  last_verified_at:number;
};

export type IntegrityFinding = {
  reasons:string[];
  foreign_projects:Array<{symbol:string;english_name:string;korean_name:string;signals:string[]}>;
};

const clean=(value:unknown)=>String(value??'').trim();
const genericWords=new Set(['token','coin','network','protocol','finance','foundation','project','ecosystem','platform','labs','dao']);
const genericTickers=new Set(['AI','NFT','DAO','DEX','AMM','EVM','API','P2P','POS','POW','TVL','L1','L2','USD','KRW','USDT','USDC']);
export function normName(value:unknown){return clean(value).toLowerCase().replace(/[^a-z0-9가-힣]+/g,'')}
function nameTokens(value:unknown){return clean(value).toLowerCase().match(/[a-z0-9]+/g)?.filter(x=>!genericWords.has(x))||[]}
export function sameProjectName(a:unknown,b:unknown){const x=normName(a),y=normName(b);if(!x||!y)return true;if(x===y)return true;if(x.length>=5&&y.length>=5&&(x.includes(y)||y.includes(x)))return true;const aa=new Set(nameTokens(a)),bb=new Set(nameTokens(b));if(!aa.size||!bb.size)return false;let hit=0;for(const t of aa)if(bb.has(t))hit++;return hit/Math.max(aa.size,bb.size)>=.8}
function symbolOf(market:unknown){return clean(market).toUpperCase().replace(/^(KRW|USDT)-/,'')}
function tickerHit(text:string,symbol:string){if(!symbol||genericTickers.has(symbol)||symbol.length<2)return false;return new RegExp(`(^|[^A-Z0-9])${symbol.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}([^A-Z0-9]|$)`).test(text.toUpperCase())}
function jsonArray(value:unknown):any[]{try{const parsed=JSON.parse(clean(value)||'[]');return Array.isArray(parsed)?parsed:[]}catch{return[]}}
function urlText(value:unknown){try{const url=new URL(clean(value));return `${url.hostname}${url.pathname}`.toLowerCase()}catch{return''}}

export function knownProjects(...maps:Array<Map<string,ExchangeMarketName>>){const seen=new Set<string>();const out:Array<{market:string;symbol:string;english_name:string;korean_name:string}>=[];for(const map of maps){for(const item of map.values()){const symbol=symbolOf(item.market),key=`${symbol}|${normName(item.english_name)}`;if(!symbol||seen.has(key))continue;seen.add(key);out.push({market:item.market,symbol,english_name:clean(item.english_name),korean_name:clean(item.korean_name)})}}return out}

export function evaluateProfileIntegrity(row:ProfileIntegrityRow,official:ExchangeMarketName|undefined,known:Array<{market:string;symbol:string;english_name:string;korean_name:string}>):IntegrityFinding{
  const reasons:string[]=[];const foreign=new Map<string,{symbol:string;english_name:string;korean_name:string;signals:Set<string>}>();
  const currentSymbol=symbolOf(row.market),officialEn=clean(official?.english_name||row.english_name),officialKo=clean(official?.korean_name||row.korean_name);
  if(official?.english_name&&!sameProjectName(row.english_name,official.english_name))reasons.push('cached_name_mismatch');
  const lead=clean(row.business_summary_ko||row.description_ko||row.description_en).slice(0,700),leadNorm=normName(lead.slice(0,260)),leadStart=normName(lead.slice(0,160));
  const currentAppears=Boolean((normName(officialEn).length>=4&&leadNorm.includes(normName(officialEn)))||(normName(officialKo).length>=2&&leadNorm.includes(normName(officialKo))));
  const evidence=jsonArray(row.evidence_json),homeText=urlText(row.homepage),providerNorm=normName(row.provider_id);
  const add=(project:{symbol:string;english_name:string;korean_name:string},signal:string)=>{const key=`${project.symbol}|${normName(project.english_name)}`;let hit=foreign.get(key);if(!hit){hit={symbol:project.symbol,english_name:project.english_name,korean_name:project.korean_name,signals:new Set()};foreign.set(key,hit)}hit.signals.add(signal)};
  for(const project of known){if(project.symbol===currentSymbol&&sameProjectName(project.english_name,officialEn))continue;const foreignEn=normName(project.english_name),foreignKo=normName(project.korean_name);if(foreignEn.length<5)continue;
    const foreignLead=leadNorm.includes(foreignEn)||(foreignKo.length>=2&&leadNorm.includes(foreignKo));
    const foreignLeadStart=leadStart.startsWith(foreignEn)||(foreignKo.length>=2&&leadStart.startsWith(foreignKo));
    if(!currentAppears&&foreignLead&&(foreignLeadStart||tickerHit(lead.slice(0,520),project.symbol)))add(project,'content_foreign_identity');
    if(providerNorm&&providerNorm.length>=4&&(providerNorm===foreignEn||providerNorm.includes(foreignEn)||foreignEn.includes(providerNorm))&&!sameProjectName(project.english_name,officialEn))add(project,'provider_foreign_identity');
    if(homeText&&homeText.replace(/[^a-z0-9]+/g,'').includes(foreignEn)&&!sameProjectName(project.english_name,officialEn))add(project,'homepage_foreign_identity');
    for(const item of evidence){if(!item||typeof item!=='object')continue;const source=clean(item.source),label=clean(item.label),url=urlText(item.url);if(source==='official_site'&&label&&sameProjectName(label,project.english_name)&&!sameProjectName(label,officialEn))add(project,'evidence_foreign_identity');if((source==='coinmarketcap'||source==='coingecko'||source==='official_site')&&url&&url.replace(/[^a-z0-9]+/g,'').includes(foreignEn)&&!sameProjectName(project.english_name,officialEn))add(project,'evidence_url_foreign_identity')}
  }
  for(const item of foreign.values())for(const signal of item.signals)if(!reasons.includes(signal))reasons.push(signal);
  return{reasons,foreign_projects:[...foreign.values()].slice(0,8).map(item=>({symbol:item.symbol,english_name:item.english_name,korean_name:item.korean_name,signals:[...item.signals]}))};
}
