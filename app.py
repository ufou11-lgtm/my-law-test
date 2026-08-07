import os
import streamlit as st
import requests
import urllib.parse
import base64

def load_api_key():
    key = os.environ.get("OC_KEY")
    if key: return key
    try:
        return st.secrets["OC_KEY"]
    except Exception:
        return None

API_KEY = load_api_key()
if not API_KEY:
    st.error(
        "🚨 API 키가 설정되지 않았습니다.\n\n"
        "- Cloud Run: 환경 변수에 OC_KEY 추가\n"
        "- 로컬: .streamlit/secrets.toml 에 OC_KEY 추가"
    )
    st.stop()

REQUEST_TIMEOUT = 15

st.set_page_config(page_title="스마트 법규 검토 시스템", page_icon="⚖️", layout="wide")
st.title("⚖️ 스마트 법규 검토 시스템 (실무형 통합 검색)")
st.markdown("건축 용어(**건폐율, 단열재의 두께, 주차장** 등)를 입력하고 **엔터(Enter)**를 누르세요. 조문과 별표 PDF를 화면에 바로 띄워줍니다.")

# 타겟 법령 매핑 사전
KEYWORD_TO_LAW_MAP = {
    "단열": ["건축물의 에너지절약설계기준", "건축법 시행령"],
    "두께": ["건축물의 에너지절약설계기준"],
    "건폐": ["건축법", "국토의 계획 및 이용에 관한 법률"],
    "용적": ["건축법", "국토의 계획 및 이용에 관한 법률"],
    "주차": ["주차장법", "주차장법 시행규칙", "주차장법 시행령"],
    "피난": ["건축물의 피난ㆍ방화구조 등의 기준에 관한 규칙", "건축법 시행령"]
}

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_api_json(url, params):
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}

@st.cache_data(show_spinner=False, ttl=1800)
def get_pdf_base64(pdf_url):
    """PDF 파일을 다운로드하여 스트림릿 화면에 바로 띄우기 위해 Base64로 변환합니다."""
    try:
        resp = requests.get(pdf_url, timeout=10)
        if resp.status_code == 200:
            return base64.b64encode(resp.content).decode('utf-8')
    except Exception:
        pass
    return None

def extract_jo_byl(data):
    jo_list = []
    byl_list = []
    
    def traverse(node):
        if isinstance(node, dict):
            if "joCntt" in node or "조문내용" in node:
                jo_list.append(node)
            if "bylSj" in node or "별표제목" in node or "별표명" in node or "bylPdfLink" in node:
                byl_list.append(node)
            for v in node.values():
                traverse(v)
        elif isinstance(node, list):
            for item in node:
                traverse(item)
                
    traverse(data)
    return jo_list, byl_list

with st.form(key="search_form"):
    search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 단열재의 두께)")
    submit_button = st.form_submit_button("🔍 법 조문 및 별표 PDF 바로 띄우기")

if submit_button:
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        # 💡 [해결 포인트 1] 조문 및 조사('의', '은', '는', '이', '가')를 깔끔하게 제거하여 핵심 키워드만 추출
        raw_tokens = search_keyword.split()
        clean_tokens = [re.sub(r'(의|를|을|은|는|이|가)$', '', tok) for tok in raw_tokens]
        clean_tokens = [tok for tok in clean_tokens if len(tok) >= 2] # 2글자 이상인 의미 있는 단어만 채택
        
        if not clean_tokens:
            clean_tokens = raw_tokens # 너무 짧으면 원본 유지

        laws_to_search = set()
        for key, laws in KEYWORD_TO_LAW_MAP.items():
            if key in search_keyword:
                laws_to_search.update(laws)
        
        if not laws_to_search:
            laws_to_search.add(raw_tokens[0])
            laws_to_search.add("건축법")

        total_found_count = 0
        
        with st.status("⚙️ **법령 및 별표 데이터 정밀 분석 중...**", expanded=True) as status:
            st.write(f"▶️ 타겟 법령: `{', '.join(laws_to_search)}` | 추출된 핵심 키워드: `{clean_tokens}`")
            
            targets = [{"code": "law", "label": "법령"}, {"code": "admrul", "label": "행정규칙"}]

            for t in targets:
                for law_name in laws_to_search:
                    list_params = {"OC": API_KEY, "target": t["code"], "type": "JSON", "query": law_name}
                    list_data = fetch_api_json("https://www.law.go.kr/DRF/lawSearch.do", list_params)
                    
                    if not list_data or not isinstance(list_data, dict):
                        continue
                    
                    search_root = list(list_data.values())[0] if list_data.values() else {}
                    items = []
                    for k, v in search_root.items():
                        if isinstance(v, list):
                            items.extend(v)

                    for item in items:
                        item_name = item.get("법령명한글") or item.get("행정규칙명") or "이름 없음"
                        item_link = item.get("법령상세링크") or item.get("행정규칙상세링크")
                        
                        if not item_link:
                            continue

                        parsed = urllib.parse.urlparse(item_link)
                        qs = urllib.parse.parse_qs(parsed.query)
                        
                        detail_params = {"OC": API_KEY, "target": t["code"], "type": "JSON"}
                        if 'MST' in qs: detail_params['MST'] = qs['MST'][0]
                        if 'ID' in qs: detail_params['ID'] = qs['ID'][0]
                        if 'admRulSeq' in qs: detail_params['ID'] = qs['admRulSeq'][0]
                        
                        detail_data = fetch_api_json("https://www.law.go.kr/DRF/lawService.do", detail_params)
                        if not detail_data or not isinstance(detail_data, dict):
                            continue
                            
                        jo_list, byl_list = extract_jo_byl(detail_data)
                        
                        found_articles = []
                        byeonpyo_matches = []

                        for jo in jo_list:
                            jo_no = str(jo.get("joNo") or jo.get("조문번호") or "")
                            jo_title = str(jo.get("joSj") or jo.get("조문제목") or "")
                            jo_content = str(jo.get("joCntt") or jo.get("조문내용") or "")
                            
                            text_to_search = jo_title + " " + jo_content
                            # 핵심 키워드 중 절반 이상이 포함되면 인정
                            if sum(1 for tok in clean_tokens if tok in text_to_search) >= len(clean_tokens) * 0.5:
                                found_articles.append({
                                    "no": jo_no,
                                    "title": jo_title,
                                    "content": jo_content
                                })

                        for byl in byl_list:
                            title = str(byl.get("bylSj") or byl.get("별표제목") or byl.get("별표명") or "")
                            
                            # 💡 [해결 포인트 2] 별표 제목에 '단열재' 또는 '두께'가 포함되어 있는지 유연하게 검사
                            if any(tok in title for tok in clean_tokens):
                                pdf_path = byl.get("bylPdfLink") or byl.get("별표서식PDF파일링크") or ""
                                hwp_path = byl.get("bylHwpLink") or byl.get("별표서식파일링크") or ""
                                
                                pdf_full_url = f"https://www.law.go.kr{pdf_path}" if pdf_path else None
                                hwp_full_url = f"https://www.law.go.kr{hwp_path}" if hwp_path else None
                                
                                byeonpyo_matches.append({
                                    "title": title,
                                    "pdf_url": pdf_full_url,
                                    "hwp_url": hwp_full_url
                                })

                        if found_articles or byeonpyo_matches:
                            total_found_count += 1
                            
                            with st.container(): 
                                with st.expander(f"🎯 [{t['label']}] {item_name} (결과 열기)", expanded=True):
                                    
                                    if found_articles:
                                        st.markdown("### 📜 관련 법 조문")
                                        for art in found_articles[:5]: 
                                            st.markdown(f"**제{art['no']}조({art['title']})**")
                                            st.markdown(f"> {art['content']}")
                                            st.divider()

                                    if byeonpyo_matches:
                                        st.markdown("### 📎 관련 별표 PDF 미리보기")
                                        for bp in byeonpyo_matches:
                                            st.markdown(f"**{bp['title']}**")
                                            
                                            # 💡 [해결 포인트 3] PDF 파일을 다운로드해 창 안에 곧바로 렌더링(Iframe)
                                            if bp['pdf_url']:
                                                with st.spinner("PDF 문서를 화면에 불러오는 중입니다..."):
                                                    pdf_b64 = get_pdf_base64(bp['pdf_url'])
                                                    if pdf_b64:
                                                        st.markdown(
                                                            f'<iframe src="data:application/pdf;base64,{pdf_b64}" width="100%" height="700px" type="application/pdf"></iframe>',
                                                            unsafe_allow_html=True
                                                        )
                                                    else:
                                                        st.markdown(f"👉 [PDF 파일 다운로드 링크]({bp['pdf_url']})")
                                            
                                            if bp['hwp_url']:
                                                st.markdown(f"🔗 [HWP 파일 다운로드]({bp['hwp_url']})")
                                            st.write("") 

            if total_found_count > 0:
                status.update(label=f"✅ 분석 완료! 총 {total_found_count}개의 문서를 찾았습니다.", state="complete", expanded=False)
            else:
                status.update(label="❌ 일치하는 문서를 찾지 못했습니다.", state="error", expanded=True)

        if total_found_count == 0:
            st.info("검색어가 너무 길거나 정확하지 않을 수 있습니다. '단열재' 또는 '에너지'처럼 단독 키워드로 검색해 보세요.")
        else:
            st.toast('성공적으로 불러왔습니다!', icon='🎉')
