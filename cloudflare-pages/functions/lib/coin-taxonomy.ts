export type SectorInfo = {
  label: string;
  summary: string;
  business: string;
};

const INFO: Record<string, SectorInfo> = {
  '메이저': {label:'메이저',summary:'비트코인·이더리움처럼 시장 전체의 유동성과 위험선호를 대표하는 핵심 자산군입니다.',business:'가치 저장, 결제·정산, 스마트컨트랙트 실행과 같은 블록체인 시장의 기본 인프라 역할을 합니다.'},
  '스테이블코인': {label:'스테이블코인',summary:'달러 등 외부 기준자산에 가격을 연동해 변동성을 낮추도록 설계된 디지털 자산입니다.',business:'거래소 결제통화, 온체인 송금, 담보·대출, 유동성 공급과 디지털 달러 결제에 주로 쓰입니다.'},
  '레이어1': {label:'레이어1',summary:'자체 합의와 검증자 네트워크를 운영하는 독립 블록체인 플랫폼입니다.',business:'스마트컨트랙트와 앱이 직접 실행되는 기반 네트워크를 제공하고 트랜잭션 수수료·스테이킹 경제를 형성합니다.'},
  '레이어2': {label:'레이어2',summary:'이더리움 등 기반 체인 위에서 처리량과 비용을 개선하는 확장 네트워크입니다.',business:'롤업·ZK·사이드체인 방식으로 거래를 묶어 처리하고 메인체인의 보안성을 활용해 앱 확장성을 높입니다.'},
  '모듈러·DA': {label:'모듈러·DA',summary:'실행·합의·정산·데이터가용성 기능을 분리해 블록체인을 조립식으로 확장하는 인프라입니다.',business:'롤업과 앱체인에 데이터 가용성, 공유 시퀀싱, 정산·검증 계층을 제공해 체인 구축 비용과 처리부하를 줄입니다.'},
  'ZK 인프라': {label:'ZK 인프라',summary:'영지식증명으로 계산의 정당성이나 개인정보를 원문 공개 없이 검증하는 기술군입니다.',business:'ZK 증명 생성·검증, zkVM, 프라이버시 연산, 롤업 검증과 검증 가능한 컴퓨팅 인프라를 제공합니다.'},
  '비트코인 생태계': {label:'비트코인 생태계',summary:'비트코인 네트워크의 확장, 스마트계약, 자산 발행과 활용을 지원하는 프로젝트군입니다.',business:'비트코인 기반 앱, 확장 네트워크, 오디널·토큰 발행, 스테이킹·브리지 같은 활용 계층을 만듭니다.'},
  '디파이': {label:'디파이',summary:'중앙 중개기관 없이 온체인에서 금융 서비스를 제공하는 프로토콜군입니다.',business:'대출·차입, 파생상품, 수익 전략, 담보 관리와 자산 운용을 스마트컨트랙트로 자동화합니다.'},
  'DEX·유동성': {label:'DEX·유동성',summary:'탈중앙화 거래와 온체인 유동성 공급을 중심으로 하는 프로토콜입니다.',business:'AMM·오더북·애그리게이터를 통해 토큰 교환, 유동성 풀, 거래 라우팅과 수수료 시장을 제공합니다.'},
  '애그리게이터': {label:'애그리게이터',summary:'여러 거래소·체인·유동성 소스를 한 번에 비교하고 최적 경로를 찾는 서비스군입니다.',business:'DEX 라우팅, 브리지 경로, 수익률·데이터를 통합해 사용자가 여러 프로토콜을 한 화면에서 이용하도록 합니다.'},
  '대출·스테이킹': {label:'대출·스테이킹',summary:'담보 대출, 스테이킹, 리스테이킹과 이자·수익 시장을 다루는 프로토콜입니다.',business:'예치 자산을 담보·검증 자본으로 활용해 이자, 스테이킹 보상, 유동성 스테이킹 토큰 등을 제공합니다.'},
  'AI·데이터': {label:'AI·데이터',summary:'인공지능 연산, 모델·에이전트, 데이터 유통과 분석 인프라를 결합한 프로젝트군입니다.',business:'분산 GPU·컴퓨팅, 데이터 마켓, AI 에이전트, 모델 접근권한과 데이터 인덱싱·분석 서비스를 제공합니다.'},
  '데이터 인프라': {label:'데이터 인프라',summary:'온체인·오프체인 데이터를 수집·색인·쿼리·검증해 다른 앱이 활용하도록 하는 인프라입니다.',business:'블록체인 인덱싱, 분석 API, 데이터 가용성·쿼리, 데이터 마켓과 개발자용 데이터 파이프라인을 제공합니다.'},
  '게임·메타버스': {label:'게임·메타버스',summary:'게임 경제, 가상세계와 디지털 아이템 소유권을 블록체인에 연결하는 프로젝트군입니다.',business:'게임 아이템·NFT, 게임 토큰 경제, 플레이어 보상, 게임 전용 네트워크와 가상세계 서비스를 운영합니다.'},
  '밈': {label:'밈',summary:'인터넷 문화와 커뮤니티 참여를 중심으로 가치와 유동성이 형성되는 토큰군입니다.',business:'기술적 효용보다 커뮤니티, 브랜드, 밈 확산과 거래 유동성이 핵심이며 일부는 결제·앱 기능을 추가합니다.'},
  'RWA': {label:'RWA',summary:'채권·부동산·신용·원자재 같은 현실 자산의 권리나 현금흐름을 온체인으로 연결하는 분야입니다.',business:'실물·금융자산 토큰화, 온체인 펀드, 신용시장, 담보와 정산 인프라를 제공합니다.'},
  '결제·송금': {label:'결제·송금',summary:'빠른 가치 이전과 국제 송금, 상거래 결제를 주요 사용처로 두는 자산군입니다.',business:'개인·기업 간 송금, 결제 네트워크, 브리지 통화와 정산 수단을 제공하는 데 초점을 둡니다.'},
  '오라클': {label:'오라클',summary:'블록체인 밖의 가격·이벤트·데이터를 스마트컨트랙트가 사용할 수 있게 전달하는 인프라입니다.',business:'가격 피드, 검증 가능한 외부 데이터, 자동화 트리거와 크로스체인 메시지를 제공합니다.'},
  '인프라·상호운용성': {label:'인프라·상호운용성',summary:'체인 간 연결, 개발도구와 블록체인 운영 기반을 제공하는 프로젝트군입니다.',business:'브리지·메시징, 노드·RPC, 체인 추상화, 크로스체인 통신과 개발자 인프라를 제공합니다.'},
  'DePIN·스토리지': {label:'DePIN·스토리지',summary:'컴퓨팅·저장공간·통신망 같은 실제 인프라 자원을 토큰 인센티브로 연결하는 분야입니다.',business:'분산 저장, GPU·컴퓨팅, 무선망, 영상·대역폭 등 물리·디지털 자원을 네트워크로 공급합니다.'},
  '프라이버시': {label:'프라이버시',summary:'거래정보와 사용자 데이터를 선택적으로 숨기거나 보호하는 기술을 중심으로 한 프로젝트군입니다.',business:'익명 거래, 프라이버시 스마트컨트랙트와 데이터 보호 인프라를 제공합니다.'},
  'NFT·크리에이터': {label:'NFT·크리에이터',summary:'디지털 소유권, 창작물, 수집품과 NFT 거래 인프라를 중심으로 하는 프로젝트군입니다.',business:'NFT 발행·거래, 크리에이터 수익화, 디지털 멤버십과 IP 기반 온체인 소유권을 지원합니다.'},
  '거래소·유틸리티': {label:'거래소·유틸리티',summary:'거래소 또는 특정 플랫폼의 수수료·멤버십·거버넌스 기능과 연결된 토큰군입니다.',business:'거래 수수료 할인, 플랫폼 혜택, 런치패드 참여, 거버넌스와 생태계 결제 기능을 제공합니다.'},
  '소셜·아이덴티티': {label:'소셜·아이덴티티',summary:'사용자 신원, 프로필, 소셜 그래프와 커뮤니티 데이터를 온체인에 연결하는 분야입니다.',business:'탈중앙 신원, 이름 서비스, 소셜 네트워크, 자격증명과 사용자 데이터 소유권을 제공합니다.'},
  '월렛·메시징': {label:'월렛·메시징',summary:'사용자의 지갑 경험과 온체인 메시지·알림·통신을 개선하는 서비스군입니다.',business:'스마트월렛, 계정 추상화, 지갑 간 메시징, 알림, 주소록과 사용자 인터페이스 인프라를 제공합니다.'},
  '팬·엔터테인먼트': {label:'팬·엔터테인먼트',summary:'스포츠·음악·엔터테인먼트 IP와 팬 참여를 토큰 경제로 연결하는 프로젝트군입니다.',business:'팬 투표, 멤버십, 디지털 굿즈, 티켓·리워드와 IP 기반 커뮤니티 참여 기능을 제공합니다.'},
  '광고·마케팅': {label:'광고·마케팅',summary:'광고 노출, 사용자 관심, 리워드와 마케팅 데이터를 블록체인 경제에 연결하는 분야입니다.',business:'광고주·퍼블리셔 정산, 주의력 보상, 캠페인 데이터와 사용자 리워드 마켓을 제공합니다.'},
  '의료·과학': {label:'의료·과학',summary:'의료·생명과학·연구 데이터와 연구자금 조달을 블록체인에 연결하는 분야입니다.',business:'의료데이터 권한, 연구 IP, DeSci 자금조달, 생명과학 데이터 공유와 연구 협업 인프라를 제공합니다.'},
  '크라우드펀딩': {label:'크라우드펀딩',summary:'프로젝트·창작자·공익 활동을 위한 자금 모집과 배분을 온체인으로 투명하게 관리하는 분야입니다.',business:'기부·펀딩, 보조금 배분, 커뮤니티 재원과 프로젝트 후원 과정을 스마트컨트랙트로 운영합니다.'},
  '미분류 검토': {label:'미분류 검토',summary:'대표 섹터를 확정할 근거가 아직 충분하지 않거나 여러 사업영역이 겹치는 종목입니다.',business:'공식 홈페이지·백서·거래소 설명서와 외부 카테고리를 추가 수집한 뒤 대표 섹터를 확정합니다.'},
};

const GROUPS: Record<string, string[]> = {
  '메이저':['BTC','ETH'],
  '스테이블코인':['USDT','USDC','DAI','FDUSD','TUSD','USDE','PYUSD','USDS','FRAX','EURC','GHO','LUSD'],
  '레이어1':['SOL','ADA','AVAX','SUI','APT','SEI','NEAR','TON','HBAR','ICP','ATOM','DOT','ALGO','KAS','EGLD','INJ','CELO','XTZ','MINA','TRX','XDC','VET','EOS','FLOW','KAVA','ONE','ZIL','QTUM','NEO','ASTR','FLR','CORE','KAIA','KLAY','ROSE','IOTA','WAVES','MOVR','GLMR','SAGA'],
  '레이어2':['ARB','OP','STRK','ZK','MNT','METIS','POL','IMX','BLAST','MODE','SKL','BOBA','LRC','MANTA','TAIKO','ZETA'],
  '모듈러·DA':['TIA','DYM','ALT','NTRN'],
  '비트코인 생태계':['STX','ORDI','SATS','RATS','MERL','BB','CKB'],
  'DEX·유동성':['UNI','SUSHI','DYDX','CAKE','GMX','BAL','CVX','JUP','COW','RAY','ORCA','ZRX','JOE','VELO','AERO','KNC','DODO','OSMO'],
  '애그리게이터':['1INCH','JUP','ODOS','PARASWAP'],
  '대출·스테이킹':['AAVE','COMP','LDO','JTO','PENDLE','ENA','EIGEN','ETHFI','REZ','RPL','SSV','ANKR','FXS','MORPHO','PUFFER'],
  '디파이':['MKR','SKY','SNX','RUNE','YFI','UMA','SPELL','CRV','ALCX','BADGER','BNT','GNO','SAFE','TRU','CPOOL','LISTA','RDNT'],
  'AI·데이터':['FET','TAO','RENDER','RNDR','WLD','IO','ATH','ARKM','VIRTUAL','AIXBT','AKT','NMR','OCEAN','AGIX','PHB','KAITO','COOKIE','GRASS','OLAS','CTXC','PAAL'],
  '데이터 인프라':['GRT','MDT','RSS3','ARK','LINK'],
  '게임·메타버스':['SAND','MANA','AXS','GALA','BEAM','PIXEL','MAGIC','RON','ILV','YGG','PORTAL','MBOX','GMT','BIGTIME','PRIME','ALICE','ENJ','WAXP','GODS','PYR','ACE','XAI','NAKA'],
  '밈':['DOGE','SHIB','PEPE','BONK','FLOKI','TRUMP','PENGU','WIF','BRETT','MOG','POPCAT','BOME','MEW','TURBO','NEIRO','BABYDOGE','MEME','DEGEN','PNUT','ACT','MOODENG','HIPPO','TOSHI','SPX','CAT','PONKE'],
  'RWA':['ONDO','OM','POLYX','CFG','RIO','MPL','TRU','CPOOL','CHEX','PLUME','PRO','GFI'],
  '결제·송금':['XRP','XLM','LTC','BCH','XEC','DASH','XNO','NANO','COTI','ACH','AMP','TEL'],
  '오라클':['PYTH','API3','BAND','TRB','DIA'],
  '인프라·상호운용성':['QNT','AXL','W','ZRO','OMNI','CELR','CTSI','LAYER','SYN','POLY','PHA','POKT'],
  'DePIN·스토리지':['FIL','AR','STORJ','HNT','MOBILE','AKT','GLM','THETA','TFUEL','LPT','AIOZ','IOTX','IO','GRASS','ATH','SC'],
  '프라이버시':['XMR','ZEC','SCRT','TORN'],
  'NFT·크리에이터':['BLUR','LOOKS','APE','NFT','SUPER','RARI','AUDIO','RARE'],
  '거래소·유틸리티':['BNB','CRO','OKB','GT','KCS','LEO','BGB','MX','WOO'],
  '소셜·아이덴티티':['ENS','ID','GAL','CYBER','MASK','LENS','DESO'],
  '팬·엔터테인먼트':['CHZ','PSG','CITY','ACM','BAR','OG','ATM','JUV','SANTOS'],
};

const SYMBOL_SECTOR = new Map<string,string>();
for (const [sector, symbols] of Object.entries(GROUPS)) for (const symbol of symbols) if (!SYMBOL_SECTOR.has(symbol)) SYMBOL_SECTOR.set(symbol, sector);

const CATEGORY_RULES: Array<[string[], string]> = [
  [['stablecoin'],'스테이블코인'],
  [['zero knowledge','zero-knowledge','zk proof','zk-proofs','zkvm'],'ZK 인프라'],
  [['data availability','modular blockchain','shared sequencer'],'모듈러·DA'],
  [['layer 2','layer-2','rollup','optimistic rollup'],'레이어2'],
  [['layer 1','layer-1','smart contract platform'],'레이어1'],
  [['real world asset','real-world asset','rwa','tokenized asset','tokenized treasury'],'RWA'],
  [['dex aggregator','swap aggregator','yield aggregator'],'애그리게이터'],
  [['decentralized exchange','automated market maker','amm','dex'],'DEX·유동성'],
  [['lending','borrowing','liquid staking','restaking','staking pool'],'대출·스테이킹'],
  [['decentralized finance','defi','yield farming','derivatives'],'디파이'],
  [['artificial intelligence','machine learning','ai agent','ai agents','generative ai'],'AI·데이터'],
  [['indexing','blockchain data','data marketplace','data infrastructure','big data'],'데이터 인프라'],
  [['gaming','gamefi','metaverse'],'게임·메타버스'],
  [['meme','memecoin'],'밈'],
  [['oracle','price feed'],'오라클'],
  [['depin','decentralized physical infrastructure','decentralized storage','distributed storage','distributed computing','gpu'],'DePIN·스토리지'],
  [['privacy','anonymous'],'프라이버시'],
  [['nft','non-fungible','creator economy'],'NFT·크리에이터'],
  [['payment','payments','remittance','merchant'],'결제·송금'],
  [['exchange-based','exchange token','centralized exchange'],'거래소·유틸리티'],
  [['cross-chain','interoperability','bridge','cross chain','chain abstraction'],'인프라·상호운용성'],
  [['wallet','account abstraction','messaging protocol'],'월렛·메시징'],
  [['social','identity','decentralized identifier','socialfi'],'소셜·아이덴티티'],
  [['fan token','sports','music','entertainment'],'팬·엔터테인먼트'],
  [['advertising','ad network','attention economy'],'광고·마케팅'],
  [['desci','healthcare','medical','biotech','science'],'의료·과학'],
  [['crowdfunding','quadratic funding','grants'],'크라우드펀딩'],
  [['bitcoin ecosystem','bitcoin layer','ordinals','runes'],'비트코인 생태계'],
];

function normalizedText(values: string[]): string[] {
  return values.map(value => String(value || '').toLowerCase().replace(/[_/]+/g, ' ').replace(/\s+/g, ' ').trim()).filter(Boolean);
}

function matches(haystack: string, needle: string): boolean {
  const value = needle.toLowerCase();
  if (value.length <= 3 && /^[a-z0-9]+$/.test(value)) {
    return new RegExp(`(?:^|[^a-z0-9])${value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}(?:$|[^a-z0-9])`, 'i').test(haystack);
  }
  return haystack.includes(value);
}

function classify(values: string[]): string {
  const normalized = normalizedText(values);
  for (const [needles, sector] of CATEGORY_RULES) {
    if (normalized.some(item => needles.some(needle => matches(item, needle)))) return sector;
  }
  return '';
}

export function sectorFor(symbolRaw: string, categories: string[] = [], evidenceText = ''): string {
  const symbol = String(symbolRaw || '').trim().toUpperCase();
  const fixed = SYMBOL_SECTOR.get(symbol);
  if (fixed) return fixed;
  const categorySector = classify(categories);
  if (categorySector) return categorySector;
  const evidenceSector = classify([String(evidenceText || '').slice(0, 8000)]);
  return evidenceSector || '미분류 검토';
}

export function sectorInfo(sector: string): SectorInfo {
  return INFO[sector] || INFO['미분류 검토'];
}

export function allSectorInfo(): Record<string, SectorInfo> {
  return INFO;
}

export const TAXONOMY_SOURCE_NOTE = '거래소 공식 명칭·설명서, 프로젝트 홈페이지·백서·Docs/GitHub, CoinMarketCap·CoinGecko의 용도/기술 카테고리를 교차검증해 대표 섹터 하나로 정규화합니다. 커뮤니티 링크은 보조 근거로만 보존하며 단독으로 섹터를 확정하지 않습니다.';
