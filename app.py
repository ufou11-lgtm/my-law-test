import os
import streamlit as st
import requests
import re

def load_api_key():
    key = os.environ.get("OC_KEY")
    if key:
        return key
    try:
        return st.secrets["OC_KEY"]
    except Exception:
        return None

API_KEY = load_api_key()
if not API_KEY:
    st.error(
        "API 키가 설정되지 않았습니다.\n\n"
        "- Cloud Run이라면: 서비스 설정 > 변수 및 보안 비밀 > 환경 변수에 OC_KEY를 추가해주세요.\n"
        "- 로컬이라면: .streamlit/secrets.toml 에 OC_KEY 값을 등록해주세요."
    )
    st.stop()

REQUEST_TIMEOUT = 10

st.set_page_config(page_title="스마트 법규 검토 시스템", page_icon="⚖️")
st.title("⚖️ 스마트 법규 검토 시스템 (조문 + 별표 통합 검색)")
st.markdown("키워드를 입력하면 법 조문 본문뿐만 아니라, **'단열재의 두께'** 같은 세부 기준이 담긴 **별표(첨부표)**까지 찾아내어 보여줍니다.")

search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 건폐율, 단열재의 두께, 주차장)")

@st.cache_data(show_spinner=False, ttl=3600)
def search_list(keyword: str, target_code: str):
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    # 키워드 검색 시 유연하게 찾기 위해 핵심 단어(예: 건폐율 -> 건폐율, 단열재의 두께 -> 단열재)로도 동시 검색 지원
    params = {
        "OC": API_KEY,
        "target": target_code,
        "type": "JSON",
        "query": keyword,
    }
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_detail(item_id: str, target_code: str, link_url: str = ""):
    url = "https://www.law.go.kr/DRF/lawService.do"
    params = {
        "OC": API_KEY,
        "target": target_code,
        "type": "JSON",
        "ID": item_id,
    }
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    
    root_key = "Law" if target_code == "law" else "Admrul"
    if root_key in data and isinstance(data[root_key], str) and "일치하는 법령이 없습니다" in data[root_key]:
        if link_url:
            match = re.search(r'MST=(\d+)', link_url)
            if match:
                mst_val = match.group(1)
                params["ID"] = mst_val
                resp2 = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                resp2.raise_for_status()
                return resp2.json()
                
    return data

def find_byeonpyo(detail_root: dict, keyword: str):
    # 법제처 API 응답 구조에서 별표 데이터를 담고 있는 후보 키들
    byeonpyo_candidates = ["별표단위", "별표서식", "별표", "byeonpyo"]
    byeonpyo_list = None
    for key in byeonpyo_candidates:
        if key in detail_root:
            byeonpyo_list = detail_root[key]
            break

    if not byeonpyo_list:
        return []

    if isinstance(byeonpyo_list, dict):
        byeonpyo_list = [byeonpyo_list]

    # 검색어에서 핵심 단어 추출 (예: "단열재의 두께" -> "단열재")
    clean_keyword = keyword.replace("의", "").replace(" ", "")
    tokens = [tok for tok in keyword.split() if len(tok) >= 2]

    results = []
    for item in byeonpyo_list:
        title = (
            item.get("별표명")
            or item.get("별표제목")
            or item.get("별표서식명")
            or ""
        )
        if not title:
            continue

        # 별표 제목에 검색어나 핵심 토큰이 포함되어 있는지 확인
        title_no_space = title.replace(" ", "")
        if keyword in title or clean_keyword in title_no_space or any(tok in title for tok in tokens):
            pdf_path = item.get("별표서식PDF파일링크")
            hwp_path = item.get("별표서식파일링크")
            results.append({
                "title": title,
                "pdf_url": f"https://www.law.go.kr{pdf_path}" if pdf_path else None,
                "hwp_url": f"https://www.law.go.kr{hwp_path}" if hwp_path else None,
            })

    return results

if st.button("법령 및 별표 통합 검색하기"):
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        # 단열재 같은 고시류는 'admrul(행정규칙)', 건폐율 같은 법은 'law(법령)'에서 주로 나옵니다.
        targets = [
            {"code": "law", "label": "법령", "detail_key": "Law"},
            {"code": "admrul", "label": "행정규칙 (고시/지침)", "detail_key": "Admrul"},
        ]

        total_found_count = 0

        # 만약 사용자가 '단열재'나 '건폐율'을 쳤을 때, 관련 핵심 법령이 무조건 검색되도록 보조 검색어 리스트 구성
        search_queries = [search_keyword]
        if "단열재" in search_keyword:
            search_queries.extend(["건축물의 에너지절약설계기준", "에너지절약"])
        elif "건폐율" in search_keyword:
            search_queries.extend(["건축법", "국토의 계획 및 이용에 관한 법률"])

        with st.spinner(f"'{search_keyword}' 관련 조문과 별표(첨부표)를 분석 중입니다..."):
            for t in targets:
                collected_items = {}
                
                # 여러 보조 검색어로 중복 없이 목록 수집
                for q in search_queries:
                    try:
                        data = search_list(q, t["code"])
                    except Exception:
                        continue

                    items = []
                    if "LawSearch" in data:
                        if "law" in data["LawSearch"]:
                            items = data["LawSearch"]["law"]
                        elif "admrul" in data["LawSearch"]:
                            items = data["LawSearch"]["admrul"]

                    for itm in items:
                        iid = itm.get("법령일련번호") or itm.get("행정규칙일련번호")
                        if iid:
                            collected_items[iid] = itm

                if not collected_items:
                    continue

                # 상위 10개 문서만 상세 본문 및 별표 조사
                for item_id, item in list(collected_items.items()[:10]):
                    item_name = item.get("법령명한글") or item.get("행정규칙명") or "이름 없음"
                    item_link = item.get("법령상세링크") or item.get("행정규칙상세링크") or ""

                    try:
                        detail_data = fetch_detail(item_id, t["code"], item_link)
                    except Exception:
                        continue

                    detail_root = detail_data.get(t["detail_key"], {})
                    if isinstance(detail_root, str):
                        continue

                    found_articles = []
                    # 1. 조문 내용 검색 (예: 건폐율)
                    if "Jo" in detail_root:
                        jo_list = detail_root["Jo"]
                        if isinstance(jo_list, dict):
                            jo_list = [jo_list]

                        for jo in jo_list:
                            jo_content = jo.get("joCntt", "")
                            jo_no = jo.get("조문번호", "")
                            jo_title = jo.get("조문제목", "")
                            
                            # 검색어가 조문 내용이나 제목에 포함된 경우
                            if search_keyword in jo_content or search_keyword in jo_title or any(tok in jo_content for tok in search_keyword.split()):
                                found_articles.append({
                                    "no": jo_no,
                                    "title": jo_title,
                                    "content": jo_content
                                })

                    # 2. 별표(첨부표) 제목 검색 (예: 단열재의 두께)
                    byeonpyo_matches = find_byeonpyo(detail_root, search_keyword)

                    # 조문이나 별표 중 하나라도 매칭되면 화면에 출력!
                    if found_articles or byeonpyo_matches:
                        total_found_count += 1
                        with st.expander(f"📌 [{t['label']}] {item_name}", expanded=True):
                            
                            # 조문 결과 출력
                            if found_articles:
                                st.markdown("**📜 관련 법 조문**")
                                for art in found_articles[:3]:  # 너무 길지 않게 상위 3개만
                                    st.markdown(f"**제{art['no']}조({art['title']})**")
                                    highlighted = art['content'].replace(search_keyword, f"**{search_keyword}**")
                                    st.markdown(f"> {highlighted}")
                                    st.markdown("---")

                            # 별표 결과 출력 (단열재의 두께 등)
                            if byeonpyo_matches:
                                st.markdown("**📎 관련 별표(첨부표)**")
                                for bp in byeonpyo_matches:
                                    file_url = bp["pdf_url"] or bp["hwp_url"]
                                    file_type = "PDF" if bp["pdf_url"] else "HWP"
                                    if file_url:
                                        st.markdown(f"- **{bp['title']}** — [{file_type} 다운로드 파일 바로가기]({file_url})")
                                    else:
                                        st.markdown(f"- **{bp['title']}** (파일 링크 없음)")

                            full_link = f"https://www.law.go.kr{item_link}" if item_link else "https://www.law.go.kr"
                            st.markdown(f"[➡️ 국가법령정보센터 원문 전체 페이지 보기]({full_link})")

        if total_found_count == 0:
            st.info(f"'{search_keyword}'과(와) 일치하는 조문이나 별표를 찾지 못했습니다. 단어를 조금 더 단순하게(예: '건폐율', '단열재') 입력해 보세요.")
        else:
            st.success(f"✅ 총 {total_found_count개의 관련 문서를 찾아냈습니다!")
