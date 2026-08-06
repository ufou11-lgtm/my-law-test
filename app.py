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
st.title("⚖️ 스마트 법규 검토 시스템 (실무형 통합 검색)")
st.markdown("건축 용어(건폐율, 단열재, 주차장 등)를 입력하면, 알아서 관련 법령과 행정규칙을 찾아 **조문 내용과 별표**를 보여줍니다.")

search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 건폐율, 단열재의 두께, 주차장)")

@st.cache_data(show_spinner=False, ttl=3600)
def search_list(keyword: str, target_code: str):
    url = "https://www.law.go.kr/DRF/lawSearch.do"
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
        targets = [
            {"code": "law", "label": "법령", "detail_key": "Law"},
            {"code": "admrul", "label": "행정규칙 (고시/지침)", "detail_key": "Admrul"},
        ]

        total_found_count = 0

        # 💡 [핵심 해결책] API가 법 이름을 검색해야 하므로, 사용자가 입력한 용어에 맞춰 핵심 법령명을 자동으로 매핑합니다!
        search_queries = [search_keyword]
        
        # 건축 실무 주요 키워드 자동 매핑
        if "건폐율" in search_keyword or "용적률" in search_keyword:
            search_queries.extend(["건축법", "국토의 계획 및 이용에 관한 법률"])
        elif "단열재" in search_keyword:
            search_queries.extend(["건축물의 에너지절약설계기준", "건축법 시행령"])
        elif "주차장" in search_keyword:
            search_queries.extend(["주차장법", "주차장법 시행규칙"])
        else:
            # 일반적인 경우 건축법을 기본으로 함께 검색
            search_queries.extend(["건축법"])

        with st.spinner(f"'{search_keyword}' 관련 법 조문과 별표를 분석 중입니다..."):
            for t in targets:
                collected_items = {}
                
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

                for item_id, item in list(collected_items.items())[:10]:
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
                    if "Jo" in detail_root:
                        jo_list = detail_root["Jo"]
                        if isinstance(jo_list, dict):
                            jo_list = [jo_list]

                        for jo in jo_list:
                            jo_content = jo.get("joCntt", "")
                            jo_no = jo.get("조문번호", "")
                            jo_title = jo.get("조문제목", "")
                            
                            # 사용자가 입력한 핵심 단어가 조문 내용이나 제목에 포함된 경우 추출
                            # (예: '건폐율' 입력 시 건폐율이 포함된 조문만 쏙쏙 골라냄)
                            main_word = search_keyword.split()[0] # 첫 단어 기준 (예: 단열재의 두께 -> 단열재)
                            if main_word in jo_content or main_word in jo_title or search_keyword in jo_content:
                                found_articles.append({
                                    "no": jo_no,
                                    "title": jo_title,
                                    "content": jo_content
                                })

                    byeonpyo_matches = find_byeonpyo(detail_root, search_keyword)

                    if found_articles or byeonpyo_matches:
                        total_found_count += 1
                        with st.expander(f"📌 [{t['label']}] {item_name}", expanded=True):
                            
                            if found_articles:
                                st.markdown("**📜 관련 법 조문**")
                                for art in found_articles[:3]:
                                    st.markdown(f"**제{art['no']}조({art['title']})**")
                                    highlighted = art['content'].replace(search_keyword, f"**{search_keyword}**")
                                    st.markdown(f"> {highlighted}")
                                    st.markdown("---")

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
            st.success(f"✅ 총 {total_found_count}개의 관련 문서를 찾아냈습니다!")
