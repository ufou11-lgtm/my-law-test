import os
import streamlit as st
import requests
import urllib.parse
import re

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
st.markdown("건축 용어(**건폐율, 단열재 두께, 주차장** 등)를 입력하고 **엔터(Enter)**를 누르세요. 관련 조문과 별표를 즉시 뽑아줍니다.")

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

# 💡 [필살기 1] JSON 데이터가 어떻게 생겼든 무조건 조문과 별표만 찾아내는 재귀 탐색 함수
def extract_jo_byl(data):
    jo_list = []
    byl_list = []
    
    def traverse(node):
        if isinstance(node, dict):
            # 조문 데이터인지 식별
            if "joCntt" in node or "조문내용" in node:
                jo_list.append(node)
            # 별표 데이터인지 식별
            if "bylSj" in node or "별표제목" in node or "별표명" in node or "bylPdfLink" in node:
                byl_list.append(node)
            
            # 딕셔너리 내부 계속 파고들기
            for v in node.values():
                traverse(v)
        elif isinstance(node, list):
            # 리스트 내부 계속 파고들기
            for item in node:
                traverse(item)
                
    traverse(data)
    return jo_list, byl_list

with st.form(key="search_form"):
    search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 단열재 두께)")
    submit_button = st.form_submit_button("🔍 법 조문 및 별표 바로 찾기")

if submit_button:
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        # 사용자가 입력한 검색어를 쪼갭니다 (예: ["단열재", "두께"])
        search_tokens = search_keyword.split()
        
        laws_to_search = set()
        for key, laws in KEYWORD_TO_LAW_MAP.items():
            if key in search_keyword:
                laws_to_search.update(laws)
        
        if not laws_to_search:
            laws_to_search.add(search_tokens[0])
            laws_to_search.add("건축법")

        total_found_count = 0
        
        with st.status("⚙️ **인공지능 법률 검토 엔진 가동 중...** (잠시만 기다려주세요)", expanded=True) as status:
            st.write(f"▶️ 타겟 법령/규칙 리스트: `{', '.join(laws_to_search)}`")
            
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

                        # 💡 [필살기 2] 확실한 파라미터 추출로 통신 에러 원천 차단
                        parsed = urllib.parse.urlparse(item_link)
                        qs = urllib.parse.parse_qs(parsed.query)
                        
                        detail_params = {"OC": API_KEY, "target": t["code"], "type": "JSON"}
                        if 'MST' in qs: detail_params['MST'] = qs['MST'][0]
                        if 'ID' in qs: detail_params['ID'] = qs['ID'][0]
                        if 'admRulSeq' in qs: detail_params['ID'] = qs['admRulSeq'][0]
                        
                        detail_data = fetch_api_json("https://www.law.go.kr/DRF/lawService.do", detail_params)
                        if not detail_data or not isinstance(detail_data, dict):
                            continue
                            
                        # 앞서 만든 재귀 탐색기로 조문과 별표만 깔끔하게 추출
                        jo_list, byl_list = extract_jo_byl(detail_data)
                        
                        found_articles = []
                        byeonpyo_matches = []

                        # 💡 [필살기 3] 엉뚱한 법령 차단을 위해 오직 '제목'과 '본문'만 검사합니다.
                        for jo in jo_list:
                            jo_no = str(jo.get("joNo") or jo.get("조문번호") or "")
                            jo_title = str(jo.get("joSj") or jo.get("조문제목") or "")
                            jo_content = str(jo.get("joCntt") or jo.get("조문내용") or "")
                            
                            text_to_search = jo_title + " " + jo_content
                            if all(token in text_to_search for token in search_tokens):
                                found_articles.append({
                                    "no": jo_no,
                                    "title": jo_title,
                                    "content": jo_content
                                })

                        for byl in byl_list:
                            title = str(byl.get("bylSj") or byl.get("별표제목") or byl.get("별표명") or "")
                            
                            # 별표는 오직 '제목(예: [별표3] 단열재의 두께)'에 검색어가 모두 포함될 때만 합격!
                            if all(token in title for token in search_tokens):
                                pdf_url = byl.get("bylPdfLink") or byl.get("별표서식PDF파일링크") or ""
                                hwp_url = byl.get("bylHwpLink") or byl.get("별표서식파일링크") or ""
                                
                                byeonpyo_matches.append({
                                    "title": title,
                                    "pdf_url": f"https://www.law.go.kr{pdf_url}" if pdf_url else None,
                                    "hwp_url": f"https://www.law.go.kr{hwp_url}" if hwp_url else None,
                                })

                        # 정확히 매칭된 결과가 있을 때만 화면에 출력 (노이즈 완벽 제거)
                        if found_articles or byeonpyo_matches:
                            total_found_count += 1
                            
                            with st.container(): 
                                with st.expander(f"🎯 [{t['label']}] {item_name} (클릭하여 열기)", expanded=True):
                                    
                                    if found_articles:
                                        st.markdown("### 📜 관련 법 조문")
                                        for art in found_articles[:5]: 
                                            st.markdown(f"**제{art['no']}조({art['title']})**")
                                            highlighted = art['content']
                                            for token in search_tokens:
                                                highlighted = highlighted.replace(token, f"**<span style='color:red; background-color:#ffe6e6;'>{token}</span>**")
                                            st.markdown(f"> {highlighted}", unsafe_allow_html=True)
                                            st.divider()

                                    if byeonpyo_matches:
                                        st.markdown("### 📎 관련 별표 및 서식")
                                        for bp in byeonpyo_matches:
                                            st.markdown(f"**{bp['title']}**")
                                            # PDF 버튼을 크고 눈에 띄게 구성
                                            if bp['pdf_url']:
                                                st.markdown(f"👉 **[PDF 파일 열기 및 다운로드]({bp['pdf_url']})**")
                                            if bp['hwp_url']:
                                                st.markdown(f"👉 **[HWP 파일 열기 및 다운로드]({bp['hwp_url']})**")
                                            st.write("") 
                                    
                                    full_link = f"https://www.law.go.kr{item_link}" if item_link else "https://www.law.go.kr"
                                    st.markdown(f"[➡️ 국가법령정보센터 원문 전체 페이지 보기]({full_link})")

            if total_found_count > 0:
                status.update(label=f"✅ 법률 검토 완료! 총 {total_found_count}개의 정확한 문서를 찾았습니다.", state="complete", expanded=False)
            else:
                status.update(label="❌ 관련된 법령 데이터를 찾지 못했습니다.", state="error", expanded=True)

        if total_found_count == 0:
            st.info("조건에 완벽히 일치하는 조문/별표가 없습니다. 키워드를 한 단어로 줄여서 검색해보세요. (예: '단열재')")
        else:
            st.toast('검색을 성공적으로 완료했습니다!', icon='🎉')
