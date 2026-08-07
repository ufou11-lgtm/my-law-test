import os
import streamlit as st
import requests
import urllib.parse
import json

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
st.markdown("건축 용어(**건폐율, 단열재 두께, 주차장** 등)를 입력하고 **엔터(Enter)**를 누르세요. 시스템이 관련 법령을 정밀 분석합니다.")

# 💡 [필살기 1] 강력한 검색어-법령 매핑 사전 (더욱 정교화됨)
KEYWORD_TO_LAW_MAP = {
    "단열": ["건축물의 에너지절약설계기준", "건축법 시행령", "건축법"],
    "두께": ["건축물의 에너지절약설계기준"],
    "건폐": ["건축법", "국토의 계획 및 이용에 관한 법률"],
    "용적": ["건축법", "국토의 계획 및 이용에 관한 법률"],
    "주차": ["주차장법", "주차장법 시행규칙", "주차장법 시행령"],
    "피난": ["건축물의 피난ㆍ방화구조 등의 기준에 관한 규칙", "건축법 시행령"]
}

def ensure_list(data):
    """딕셔너리든 리스트든 무조건 리스트로 안전하게 반환"""
    if not data: return []
    if isinstance(data, dict): return [data]
    return data

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_api_json(url, params):
    """안전한 API 호출 래퍼 함수"""
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        pass
    return {}

# 폼 구역 설정 (엔터키 입력 지원)
with st.form(key="search_form"):
    search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 단열재 두께)")
    submit_button = st.form_submit_button("🔍 법령 및 별표 정밀 분석 시작")

if submit_button:
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        # 1. 검색어 분리 (예: "단열재 두께" -> ["단열재", "두께"])
        search_tokens = search_keyword.split()
        
        # 2. 어떤 법령을 뒤질지 타겟 설정
        laws_to_search = set()
        for key, laws in KEYWORD_TO_LAW_MAP.items():
            if key in search_keyword:
                laws_to_search.update(laws)
        
        # 사전에 없으면 기본적으로 입력 첫 단어와 건축법을 검색
        if not laws_to_search:
            laws_to_search.add(search_tokens[0])
            laws_to_search.add("건축법")

        total_found_count = 0
        
        # 💡 [필살기 2] 사용자에게 시스템이 일하고 있음을 보여주는 실시간 현황판
        with st.status("⚙️ **인공지능 법률 검토 엔진 가동 중...** (잠시만 기다려주세요)", expanded=True) as status:
            st.write(f"▶️ 타겟 법령/규칙 리스트 설정 완료: `{', '.join(laws_to_search)}`")
            
            targets = [{"code": "law", "label": "법령"}, {"code": "admrul", "label": "행정규칙"}]

            for t in targets:
                for law_name in laws_to_search:
                    st.write(f"🔍 [{t['label']}] `{law_name}` 데이터베이스 조회 중...")
                    
                    # 검색 목록 가져오기
                    list_params = {"OC": API_KEY, "target": t["code"], "type": "JSON", "query": law_name}
                    list_data = fetch_api_json("https://www.law.go.kr/DRF/lawSearch.do", list_params)
                    
                    if not list_data or not isinstance(list_data, dict):
                        continue
                    
                    # API 변덕 방어: 키 이름 무시하고 첫 번째 알맹이 상자 열기
                    search_root = list(list_data.values())[0] if list_data.values() else {}
                    
                    # 법령 목록 끄집어내기
                    items = []
                    for k, v in search_root.items():
                        if isinstance(v, list):
                            items.extend(v)

                    for item in items:
                        item_name = item.get("법령명한글") or item.get("행정규칙명") or "이름 없음"
                        item_link = item.get("법령상세링크") or item.get("행정규칙상세링크")
                        
                        if not item_link:
                            continue

                        st.write(f"📥 `{item_name}` 원문 다운로드 및 형태소 분석 중...")

                        # 💡 [필살기 3] 스마트 URL 파서: API가 준 링크를 쪼개서 정확한 파라미터만 쏙 빼옵니다!
                        parsed_url = urllib.parse.urlparse(item_link)
                        query_params = urllib.parse.parse_qs(parsed_url.query)
                        
                        fetch_params = {k: v[0] for k, v in query_params.items()}
                        fetch_params['OC'] = API_KEY  # 내 API 키로 교체
                        fetch_params['type'] = 'JSON' # 무조건 JSON으로 요구
                        
                        detail_api_url = "https://www.law.go.kr" + parsed_url.path
                        detail_data = fetch_api_json(detail_api_url, fetch_params)
                        
                        if not detail_data or not isinstance(detail_data, dict):
                            continue
                            
                        # 상세 데이터 변덕 방어: 무조건 첫 번째 알맹이 접근
                        detail_root = list(detail_data.values())[0] if detail_data.values() else {}
                        
                        jo_list = ensure_list(detail_root.get("Jo") or detail_root.get("jo") or [])
                        byl_list = ensure_list(detail_root.get("Byl") or detail_root.get("byl") or detail_root.get("별표") or [])
                        
                        found_articles = []
                        byeonpyo_matches = []

                        # --- 조문(Jo) 텍스트 풀스캔 ---
                        for jo in jo_list:
                            # 딕셔너리 전체를 문자열로 바꿔서 토큰이 모두 포함되어 있는지 무식하고 확실하게 검사
                            jo_str = json.dumps(jo, ensure_ascii=False)
                            if all(token in jo_str for token in search_tokens):
                                jo_content = jo.get("joCntt") or jo.get("조문내용") or ""
                                jo_no = jo.get("조문번호") or jo.get("joNo") or ""
                                jo_title = jo.get("조문제목") or jo.get("joSj") or ""
                                
                                found_articles.append({
                                    "no": jo_no,
                                    "title": jo_title,
                                    "content": jo_content if jo_content else "하위 항목(항/호)에 검색어가 포함되어 있습니다."
                                })

                        # --- 별표(Byl) 첨부문서 풀스캔 ---
                        for byl in byl_list:
                            byl_str = json.dumps(byl, ensure_ascii=False)
                            if all(token in byl_str for token in search_tokens):
                                title = byl.get("bylSj") or byl.get("별표제목") or byl.get("별표명") or "이름 없는 별표"
                                pdf_path = byl.get("bylPdfLink") or byl.get("bylPdfUrl") or byl.get("별표서식PDF파일링크") or ""
                                hwp_path = byl.get("bylHwpLink") or byl.get("bylHwpUrl") or byl.get("별표서식파일링크") or ""
                                
                                byeonpyo_matches.append({
                                    "title": title,
                                    "pdf_url": f"https://www.law.go.kr{pdf_path}" if pdf_path else None,
                                    "hwp_url": f"https://www.law.go.kr{hwp_path}" if hwp_path else None,
                                })

                        # 결과 출력부
                        if found_articles or byeonpyo_matches:
                            total_found_count += 1
                            st.write(f"🎯 **발견!** `{item_name}`에서 관련 조문/별표를 찾았습니다.")
                            
                            with st.container(): # status 상자 바깥쪽에 렌더링되게끔 처리
                                with st.expander(f"📌 [{t['label']}] {item_name} 상세 결과 보기", expanded=True):
                                    
                                    if found_articles:
                                        st.markdown("### 📜 관련 법 조문")
                                        for art in found_articles[:5]: # 최대 5개 노출
                                            st.markdown(f"**제{art['no']}조({art['title']})**")
                                            highlighted = art['content']
                                            for token in search_tokens:
                                                highlighted = highlighted.replace(token, f"**<span style='color:#ff4b4b; background-color:#ffe6e6;'>{token}</span>**")
                                            st.markdown(f"> {highlighted}", unsafe_allow_html=True)
                                            st.divider()

                                    if byeonpyo_matches:
                                        st.markdown("### 📎 관련 별표(첨부문서)")
                                        for bp in byeonpyo_matches:
                                            st.markdown(f"**{bp['title']}**")
                                            if bp['pdf_url']:
                                                st.markdown(f"🔗 [PDF 다운로드 바로가기]({bp['pdf_url']})")
                                            if bp['hwp_url']:
                                                st.markdown(f"🔗 [HWP 다운로드 바로가기]({bp['hwp_url']})")
                                            st.write("") # 간격 띄우기
                                    
                                    full_link = f"https://www.law.go.kr{item_link}" if item_link else "https://www.law.go.kr"
                                    st.markdown(f"[➡️ 국가법령정보센터 원문 전체 페이지 보기]({full_link})")

            # 상태 업데이트
            if total_found_count > 0:
                status.update(label=f"✅ 법률 검토 완료! 총 {total_found_count}개의 문서를 찾았습니다.", state="complete", expanded=False)
            else:
                status.update(label="❌ 관련된 법령 데이터를 찾지 못했습니다.", state="error", expanded=True)

        # 최종 메시지
        if total_found_count == 0:
            st.info("조건에 완벽히 일치하는 데이터가 없습니다. 키워드를 한 단어로 줄여서 검색해보세요. (예: '단열재')")
        else:
            st.balloons() # 성공 시 풍선 애니메이션 축하!
