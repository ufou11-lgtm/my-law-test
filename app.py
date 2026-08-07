import os
import streamlit as st
import requests
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
        "- Cloud Run: 서비스 설정 > 변수 및 보안 비밀 > 환경 변수에 OC_KEY 추가\n"
        "- 로컬: .streamlit/secrets.toml 에 OC_KEY 추가"
    )
    st.stop()

REQUEST_TIMEOUT = 10

st.set_page_config(page_title="스마트 법규 검토 시스템", page_icon="⚖️", layout="wide")
st.title("⚖️ 스마트 법규 검토 시스템 (실무형 통합 검색)")
st.markdown("건축 용어(**건폐율, 단열재, 주차장** 등)를 입력하면, 관련된 법령/행정규칙의 **조문과 별표**를 자동으로 찾아줍니다.")

# 💡 [해결 포인트] 매핑 사전에 "건축법"을 보강했습니다.
KEYWORD_TO_LAW_MAP = {
    "단열": ["건축물의 에너지절약설계기준", "건축법 시행령", "건축법"],
    "건폐": ["건축법", "국토의 계획 및 이용에 관한 법률"],
    "용적": ["건축법", "국토의 계획 및 이용에 관한 법률"],
    "주차": ["주차장법", "주차장법 시행규칙"],
    "피난": ["건축물의 피난ㆍ방화구조 등의 기준에 관한 규칙", "건축법 시행령"]
}

search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 단열재 두께, 건폐율 확인)")

@st.cache_data(show_spinner=False, ttl=3600)
def search_list(law_name: str, target_code: str):
    """법령명으로 API를 호출하여 검색 리스트를 가져옵니다."""
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {"OC": API_KEY, "target": target_code, "type": "JSON", "query": law_name}
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        return {}
    return resp.json()

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_detail(item_link: str, target_code: str):
    """💡 [해결 포인트] API가 준 상세 링크에서 가장 정확한 파라미터(MST 또는 ID)를 쏙 빼옵니다."""
    url = "https://www.law.go.kr/DRF/lawService.do"
    params = {"OC": API_KEY, "target": target_code, "type": "JSON"}
    
    match_mst = re.search(r'MST=(\d+)', item_link)
    match_id = re.search(r'ID=(\d+)', item_link)
    
    if match_mst:
        params["MST"] = match_mst.group(1)
    elif match_id:
        params["ID"] = match_id.group(1)
    else:
        return {}

    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        return {}
    return resp.json()

def ensure_list(data):
    if not data: return []
    if isinstance(data, dict): return [data]
    return data

def find_byeonpyo(detail_root: dict, search_tokens: list):
    """별표(첨부문서) 제목에 검색어가 유연하게 포함되어 있는지 확인합니다."""
    byl_data = detail_root.get("Byl") or detail_root.get("byl") or []
    byl_list = ensure_list(byl_data)

    results = []
    for item in byl_list:
        title = item.get("bylSj") or item.get("별표제목") or item.get("별표명") or ""
        if not title:
            continue
            
        # 💡 [해결 포인트] 사용자가 입력한 여러 단어 중 하나라도 별표 제목에 걸리면 노출합니다.
        if any(tok in title for tok in search_tokens):
            pdf_path = item.get("bylPdfLink") or item.get("bylPdfUrl") or item.get("별표서식PDF파일링크") or ""
            hwp_path = item.get("bylHwpLink") or item.get("bylHwpUrl") or item.get("별표서식파일링크") or ""
            
            results.append({
                "title": title,
                "pdf_url": f"https://www.law.go.kr{pdf_path}" if pdf_path else None,
                "hwp_url": f"https://www.law.go.kr{hwp_path}" if hwp_path else None,
            })
    return results

if st.button("🔍 법령 및 별표 통합 검색하기"):
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        targets = [
            {"code": "law", "label": "법령"},
            {"code": "admrul", "label": "행정규칙"},
        ]

        laws_to_search = set()
        for key, laws in KEYWORD_TO_LAW_MAP.items():
            if key in search_keyword:
                laws_to_search.update(laws)
        
        # 💡 [해결 포인트] 사전에 등록되지 않은 단어라도, 첫 단어를 법령명으로 간주해 검색을 시도합니다.
        if not laws_to_search:
            laws_to_search.add(search_keyword.split()[0])
            laws_to_search.add("건축법")

        total_found_count = 0
        search_tokens = search_keyword.split()

        with st.spinner(f"'{search_keyword}' 관련 법령(문서)을 분석 중입니다..."):
            for t in targets:
                for law_name in laws_to_search:
                    try:
                        list_data = search_list(law_name, t["code"])
                    except Exception:
                        continue

                    search_root = list_data.get("LawSearch", {})
                    if t["code"] == "law":
                        items = ensure_list(search_root.get("law", []))
                    else:
                        items = ensure_list(search_root.get("admrul", []))

                    for item in items:
                        item_link = item.get("법령상세링크") or item.get("행정규칙상세링크")
                        item_name = item.get("법령명한글") or item.get("행정규칙명") or "이름 없음"

                        if not item_link:
                            continue

                        try:
                            detail_data = fetch_detail(item_link, t["code"])
                        except Exception:
                            continue
                        
                        # JSON 루트 키가 변덕스러울 수 있어 모두 체크합니다.
                        detail_root = detail_data.get("Law") or detail_data.get("Admrul") or detail_data.get("admrul") or {}
                        if not isinstance(detail_root, dict):
                            continue

                        # 1. 조문(Jo) 검색
                        jo_list = ensure_list(detail_root.get("Jo") or detail_root.get("jo") or [])
                        found_articles = []
                        
                        for jo in jo_list:
                            # 💡 [시니어 개발자의 꼼수] 조문 딕셔너리 전체를 문자열로 바꿔버리면 깊숙이 숨은 항/호의 내용까지 쉽게 찾아낼 수 있습니다!
                            jo_str = str(jo)
                            if all(token in jo_str for token in search_tokens):
                                jo_content = jo.get("joCntt") or jo.get("조문내용") or ""
                                jo_no = jo.get("조문번호") or jo.get("joNo") or ""
                                jo_title = jo.get("조문제목") or jo.get("joSj") or ""
                                
                                # 검색어가 본문에는 없고 하위 항목(항/호)에만 있는 경우를 위한 친절한 안내
                                if not all(token in jo_content or token in jo_title for token in search_tokens):
                                    jo_content += "\n\n*(※ 검색하신 키워드가 해당 조문의 이하 '항' 또는 '호'에 포함되어 있습니다)*"

                                found_articles.append({
                                    "no": jo_no,
                                    "title": jo_title,
                                    "content": jo_content
                                })

                        # 2. 별표(Byl) 검색
                        byeonpyo_matches = find_byeonpyo(detail_root, search_tokens)

                        if found_articles or byeonpyo_matches:
                            total_found_count += 1
                            with st.expander(f"📌 [{t['label']}] {item_name}", expanded=True):
                                
                                if found_articles:
                                    st.markdown("### 📜 관련 법 조문")
                                    for art in found_articles[:5]:
                                        st.markdown(f"**제{art['no']}조({art['title']})**")
                                        highlighted = art['content']
                                        # 유저가 검색한 단어 눈에 띄게 빨간색으로 하이라이팅 처리
                                        for token in search_tokens:
                                            highlighted = highlighted.replace(token, f"**<span style='color:#ff4b4b;'>{token}</span>**")
                                        st.markdown(f"> {highlighted}", unsafe_allow_html=True)
                                        st.divider()

                                if byeonpyo_matches:
                                    st.markdown("### 📎 관련 별표(첨부표)")
                                    for bp in byeonpyo_matches:
                                        file_url = bp["pdf_url"] or bp["hwp_url"]
                                        if file_url:
                                            st.markdown(f"- **{bp['title']}** 🔗 [[파일 다운로드 바로가기]]({file_url})")
                                        else:
                                            st.markdown(f"- **{bp['title']}** (파일 링크 없음)")
                                
                                full_link = f"https://www.law.go.kr{item_link}" if item_link else "https://www.law.go.kr"
                                st.markdown(f"[➡️ 국가법령정보센터 원문 전체 페이지 보기]({full_link})")

        if total_found_count == 0:
            st.info(f"'{search_keyword}' 관련 조문이나 별표를 찾지 못했습니다. 키워드를 '단열', '건폐율' 등으로 짧게 입력해 보세요.")
        else:
            st.success(f"✅ 총 {total_found_count}개의 관련 문서를 찾아냈습니다!")
