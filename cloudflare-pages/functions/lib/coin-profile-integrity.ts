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

type KnownProject={market:string;symbol:string;english_name:string;korean_name:string};
export type IntegrityProjectIndex={
  projects:KnownProject[];
  by_name:Map<string,KnownProject[]>;
  by_symbol:Map<string,KnownProject[]>;
  name_pattern:RegExp|null;
};

const clean=(value:unknown)=>String(value??'').trim();
const genericWords=new Set(['token','coin','network','protocol','finance','foundation','project','ecosystem','platform','labs','dao']);
const genericTickers=new Set(['AI','NFT','DAO','DEX','AMM','EVM','API','P2P','POS','POW','TVL','L1','L2','USD','KRW','USDT','USDC']);
const genericLeads=new Set(['프로젝트','프로토콜','플랫폼','네트워크','생태계','블록체인','서비스','토큰']);
export function normName(value:unknown){return clean(value).toLowerCase().replace(/[^a-z0-9가-힣]+/g,'')}
function nameTokens(value:unknown){return clean(value).toLowerCase().match(/[a-z0-9]+/g)?.filter(x=>!genericWords.has(x))||[]}
export function sameProjectName(a:unknown,b:unknown){const x=normName(a),y=normName(b);if(!x||!y)return true;if(x===y)return true;if(x.length>=5&&y.length>=5&&(x.includes(y)||y.includes(x)))return true;const aa=new Set(nameTokens(a)),bb=new Set(nameTokens(b));if(!aa.size||!bb.size)return false;let hit=0;for(const t of aa)if(bb.has(t))hit++;return hit/Math.max(aa.size,bb.size)>=.8}
function symbolOf(market:unknown){return clean(market).toUpperCase().replace(/^[A-Z0-9]+-/,'')}
function tickerHit(text:string,symbol:string){if(!symbol||genericTickers.has(symbol)||symbol.length<2)return false;return new RegExp(`(^|[^A-Z0-9])${symbol.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}([^A-Z0-9]|$)`).test(text.toUpperCase())}
function jsonArray(value:unknown):any[]{try{const parsed=JSON.parse(clean(value)||'[]');return Array.isArray(parsed)?parsed:[]}catch{return[]}}
function compactLead(value:unknown){return clean(value).replace(/\s+/g,' ').replace(/\(\s+/g,'(').replace(/\s+\)/g,')').trim()}
function leadIdentity(text:string){const value=compactLead(text).slice(0,240);const match=value.match(/^([A-Za-z가-힣][A-Za-z0-9가-힣 ._&/-]{1,56}?)(?:\s*\(\s*([A-Za-z0-9][A-Za-z0-9 ._&/-]{1,48})\s*\))?\s*(?:은|는|이|가|란|라는)/);if(!match)return null;const name=clean(match[1]),alias=clean(match[2]);if(genericLeads.has(name))return null;return{name,alias}}
function escapeRegex(value:string){return value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}
function addMap(map:Map<string,KnownProject[]>,key:string,project:KnownProject){if(!key)return;const rows=map.get(key)||[];if(!rows.some(row=>row.symbol===project.symbol&&normName(row.english_name)===normName(project.english_name)))rows.push(project);map.set(key,rows)}

export function knownProjects(...maps:Array<Map<string,ExchangeMarketName>>):IntegrityProjectIndex{
  const seen=new Set<string>(),projects:KnownProject[]=[],by_name=new Map<string,KnownProject[]>(),by_symbol=new Map<string,KnownProject[]>(),aliases=new Set<string>();
  for(const map of maps){for(const item of map.values()){
    const symbol=symbolOf(item.market),key=`${symbol}|${normName(item.english_name)}`;if(!symbol||seen.has(key))continue;seen.add(key);
    const project={market:item.market,symbol,english_name:clean(item.english_name),korean_name:clean(item.korean_name)};projects.push(project);addMap(by_symbol,symbol,project);
    for(const raw of [project.english_name,project.korean_name]){const alias=normName(raw);if(!alias)continue;addMap(by_name,alias,project);const isKorean=/[가-힣]/.test(alias);if((isKorean&&alias.length>=2)||(!isKorean&&alias.length>=5))aliases.add(alias)}
  }}
  const ordered=[...aliases].sort((a,b)=>b.length-a.length||a.localeCompare(b));
  return{projects,by_name,by_symbol,name_pattern:ordered.length?new RegExp(ordered.map(escapeRegex).join('|'),'g'):null};
}

function projectsInText(index:IntegrityProjectIndex,value:unknown,limit=8){const haystack=normName(value),out:KnownProject[]=[],seen=new Set<string>(),pattern=index.name_pattern;if(!haystack||!pattern)return out;pattern.lastIndex=0;let match:RegExpExecArray|null;while((match=pattern.exec(haystack))!==null&&out.length<limit){const rows=index.by_name.get(match[0])||[];for(const project of rows){const key=`${project.symbol}|${normName(project.english_name)}`;if(seen.has(key))continue;seen.add(key);out.push(project);if(out.length>=limit)break}if(match[0]==='')pattern.lastIndex++}pattern.lastIndex=0;return out}
function projectsForIdentity(index:IntegrityProjectIndex,name:string,alias:string){const out:KnownProject[]=[],seen=new Set<string>();const candidates:KnownProject[]=[];for(const value of [name,alias]){const normalized=normName(value);if(normalized)candidates.push(...(index.by_name.get(normalized)||[]));const symbol=clean(value).toUpperCase();if(/^[A-Z0-9._-]{2,16}$/.test(symbol))candidates.push(...(index.by_symbol.get(symbol)||[]))}for(const project of candidates){const key=`${project.symbol}|${normName(project.english_name)}`;if(seen.has(key))continue;seen.add(key);out.push(project)}return out}
function projectsInUrl(index:IntegrityProjectIndex,value:unknown,limit=8){const out:KnownProject[]=[],seen=new Set<string>();let url:URL;try{url=new URL(clean(value))}catch{return out}const parts=[...url.hostname.toLowerCase().split('.'),...url.pathname.toLowerCase().split(/[^a-z0-9가-힣]+/g)].map(normName).filter(Boolean);for(const part of parts){for(const project of index.by_name.get(part)||[]){const key=`${project.symbol}|${normName(project.english_name)}`;if(seen.has(key))continue;seen.add(key);out.push(project);if(out.length>=limit)return out}}return out}
function sharedDistinctiveToken(a:unknown,b:unknown){const aa=nameTokens(a).filter(x=>x.length>=4),bb=new Set(nameTokens(b).filter(x=>x.length>=4));return aa.some(x=>bb.has(x))}
function exactLeadIsCurrent(lead:{name:string;alias:string}|null,officialEn:string,officialKo:string,currentSymbol:string){if(!lead)return false;const name=normName(lead.name),alias=clean(lead.alias).toUpperCase();const nameMatches=Boolean((normName(officialKo)&&name===normName(officialKo))||(normName(officialEn)&&name===normName(officialEn)));const aliasMatches=!alias||alias===currentSymbol||sameProjectName(lead.alias,officialEn);return nameMatches&&aliasMatches}
function currentLeadPrefixMatches(text:string,officialEn:string,officialKo:string,currentSymbol:string){const value=compactLead(text).slice(0,240),symbol=escapeRegex(currentSymbol);for(const rawName of [officialKo,officialEn]){const name=clean(rawName);if(!name)continue;const pattern=new RegExp(`^${escapeRegex(name)}\\s*(?:\\(\\s*${symbol}\\s*\\))?\\s*(?:은|는|이|가|란|라는)`,`i`);if(pattern.test(value))return true}return false}

export function evaluateProfileIntegrity(row:ProfileIntegrityRow,official:ExchangeMarketName|undefined,index:IntegrityProjectIndex):IntegrityFinding{
  const reasons:string[]=[];const foreign=new Map<string,{symbol:string;english_name:string;korean_name:string;signals:Set<string>}>();
  const currentSymbol=symbolOf(row.market),officialEn=clean(official?.english_name||row.english_name),officialKo=clean(official?.korean_name||row.korean_name);
  const isCurrent=(project:KnownProject)=>project.symbol===currentSymbol||sameProjectName(project.english_name,officialEn);
  const add=(project:KnownProject,signal:string)=>{if(isCurrent(project))return;const key=`${project.symbol}|${normName(project.english_name)}`;let hit=foreign.get(key);if(!hit){hit={symbol:project.symbol,english_name:project.english_name,korean_name:project.korean_name,signals:new Set()};foreign.set(key,hit)}hit.signals.add(signal)};
  if(official?.english_name&&!sameProjectName(row.english_name,official.english_name))reasons.push('cached_name_mismatch');
  const lead=compactLead(row.business_summary_ko||row.description_ko||row.description_en).slice(0,700),leadNorm=normName(lead.slice(0,360)),leadStart=normName(lead.slice(0,180));
  const currentAppears=Boolean((normName(officialEn).length>=4&&leadNorm.includes(normName(officialEn)))||(normName(officialKo).length>=2&&leadNorm.includes(normName(officialKo)))||tickerHit(lead.slice(0,360),currentSymbol));
  const leadId=leadIdentity(lead),leadIsCurrent=exactLeadIsCurrent(leadId,officialEn,officialKo,currentSymbol)||currentLeadPrefixMatches(lead,officialEn,officialKo,currentSymbol);
  if(leadId&&!leadIsCurrent){const identities=projectsForIdentity(index,leadId.name,leadId.alias),hasCurrent=identities.some(isCurrent),foreignIdentities=identities.filter(project=>!isCurrent(project));if(!hasCurrent&&foreignIdentities.length){reasons.push('content_lead_name_mismatch');for(const project of foreignIdentities)add(project,'content_foreign_identity')}}
  if(!currentAppears&&!leadIsCurrent){for(const project of projectsInText(index,lead.slice(0,520))){const aliases=[normName(project.english_name),normName(project.korean_name)].filter(Boolean),starts=aliases.some(alias=>leadStart.startsWith(alias));if(starts||tickerHit(lead.slice(0,520),project.symbol))add(project,'content_foreign_identity')}}
  const relatedToCurrent=(project:KnownProject)=>(currentAppears||leadIsCurrent)&&(leadNorm.includes(normName(project.english_name))||leadNorm.includes(normName(project.korean_name))||sharedDistinctiveToken(officialEn,project.english_name));
  const providerNorm=normName(row.provider_id);if(providerNorm){for(const project of projectsInText(index,providerNorm))if(!relatedToCurrent(project))add(project,'provider_foreign_identity')}
  if(row.homepage){for(const project of projectsInUrl(index,row.homepage))if(!relatedToCurrent(project))add(project,'homepage_foreign_identity')}
  const evidence=jsonArray(row.evidence_json);for(const item of evidence){if(!item||typeof item!=='object')continue;const source=clean(item.source),label=clean(item.label),url=clean(item.url);if(source==='official_site'&&label){for(const project of projectsForIdentity(index,label,''))if(!relatedToCurrent(project))add(project,'evidence_foreign_identity')}if((source==='coinmarketcap'||source==='coingecko'||source==='official_site')&&url){for(const project of projectsInUrl(index,url))if(!relatedToCurrent(project))add(project,'evidence_url_foreign_identity')}}
  for(const item of foreign.values())for(const signal of item.signals)if(!reasons.includes(signal))reasons.push(signal);
  return{reasons,foreign_projects:[...foreign.values()].slice(0,8).map(item=>({symbol:item.symbol,english_name:item.english_name,korean_name:item.korean_name,signals:[...item.signals]}))};
}