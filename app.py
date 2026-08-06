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
st.title("⚖️ 스마트 법규 검토 시스템 (조문 내용 검색)")
st.markdown("키워드를 입력하면 관련 법령을 찾고, **그 단어가 포함된 실제 법 조문 내용(예: 제55조 건폐율 등)**을 화면에 띄워줍니다.")

search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 건폐율, 용적률, 주차장)")

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

def hide_key(text: str) -> str:
    if API_KEY:
        text = text.replace(API_KEY, "********")
    return text

if st.button("법 조문 내용 검색하기"):
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        targets = [
            {"code": "law", "label": "법령", "detail_key": "Law"},
            {"code": "admrul", "label": "행정규칙", "detail_key": "Admrul"},
        ]

        total_found_count = 0

        with st.spinner(f"법령 본문에서 '{search_keyword}'(을)를 포함한 조문을 찾고 있습니다..."):
            for t in targets:
                try:
                    data = search_list(search_keyword, t["code"])
                except Exception as e:
                    continue

                items = []
                if "LawSearch" in data:
                    if "law" in data["LawSearch"]:
                        items = data["LawSearch"]["law"]
                    elif "admrul" in data["LawSearch"]:
                        items = data["LawSearch"]["admrul"]

                if not items:
                    continue

                # 속도를 위해 상위 5개 법령만 상세 본문을 뒤집니다.
                for item in items[:5]:
                    item_name = item.get("법령명한글") or item.get("행정규칙명") or "이름 없음"
                    item_id = item.get("법령일련번호") or item.get("행정규칙일련번호") or ""
                    item_link = item.get("법령상세링크") or item.get("행정규칙상세링크") or ""

                    if not item_id:
                        continue

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
                            
                            # 조문 내용이나 조문 제목에 검색어가 포함되어 있다면 수집!
                            if search_keyword in jo_content or search_keyword in jo_title:
                                found_articles.append({
                                    "no": jo_no,
                                    "title": jo_title,
                                    "content": jo_content
                                })

                    # 찾은 조문이 있다면 화면에 이쁘게 출력
                    if found_articles:
                        total_found_count += len(found_articles)
                        with st.expander(f"📌 [{t['label']}] {item_name} (관련 조문 {len(found_articles)}건 발견)", expanded=True):
                            for art in found_articles:
                                st.markdown(f"**제{art['no']}조({art['title']})**")
                                # 검색어 부분을 굵은 글씨로 강조
                                highlighted = art['content'].replace(search_keyword, f"**{search_keyword}**")
                                st.markdown(f"> {highlighted}")
                                st.markdown("---")
                            
                            full_link = f"https://www.law.go.kr{item_link}"
                            st.markdown(f"[➡️ 국가법령정보센터 원문 전체 보기]({full_link})")

        if total_found_count == 0:
            st.info(f"'{search_keyword}'(이)가 본문에 포함된 조문을 찾지 못했습니다. 키워드를 확인해보세요.")
        else:
            st.success(f"✅ 총 {total_found_count}개의 관련 조문을 찾아냈습니다!")
