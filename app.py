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
st.title("⚖️ 스마트 법규 검토 시스템 (실무 통합 검색)")
st.markdown("키워드를 입력하면 관련된 **기본 법령**과 세부 기준이 담긴 **행정규칙(고시, 지침)**을 찾아 원문 및 별표로 바로 연결해 줍니다.")

search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 단열재, 건축물 에너지, 주차장)")

@st.cache_data(show_spinner=False, ttl=3600)
def search_list(keyword: str, target_code: str):
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {
        "OC": API_KEY,
        "target": target_code,
        "type": "JSON",
        "query": keyword,
        "search": "1",  # 안전하게 통합 검색
    }
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def hide_key(text: str) -> str:
    if API_KEY:
        text = text.replace(API_KEY, "********")
    return text

if st.button("법령 및 행정규칙 검색하기"):
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        targets = [
            {"code": "law", "label": "법령"},
            {"code": "admrul", "label": "행정규칙 (고시/지침)"},
        ]

        total_results = 0

        with st.spinner(f"'{search_keyword}' 관련 법령과 행정규칙을 검색하는 중입니다..."):
            for t in targets:
                try:
                    data = search_list(search_keyword, t["code"])
                except Exception as e:
                    st.error(f"{t['label']} 검색 중 오류가 발생했습니다: {hide_key(str(e))}")
                    continue

                items = []
                if "LawSearch" in data:
                    if "law" in data["LawSearch"]:
                        items = data["LawSearch"]["law"]
                    elif "admrul" in data["LawSearch"]:
                        items = data["LawSearch"]["admrul"]

                if not items:
                    continue

                total_results += len(items)
                st.markdown(f"### 📂 관련 {t['label']} 목록 (총 {len(items)}건)")

                # 검색된 결과 상위 10개까지 깔끔하게 카드 형태로 출력
                for item in items[:10]:
                    item_name = item.get("법령명한글") or item.get("행정규칙명") or "이름 없음"
                    item_link = item.get("법령상세링크") or item.get("행정규칙상세링크") or ""
                    ef_date = item.get("시행일자") or item.get("발령일자") or "정보 없음"
                    
                    full_link = f"https://www.law.go.kr{item_link}" if item_link else "https://www.law.go.kr"

                    with st.expander(f"📌 {item_name} (시행일: {ef_date})"):
                        st.markdown(f"- **문서 종류:** {t['label']}")
                        st.markdown(f"- **상세 내용 및 별표 확인:** [국가법령정보센터 원문 및 별표 바로가기]({full_link})")
                        st.info("💡 단열재 두께, 주차장 대수 등의 구체적인 수치 기준은 원문 페이지 내의 **[별표/서식]** 탭에서 PDF 또는 HWP 파일로 확인하실 수 있습니다.")

        if total_results == 0:
            st.info(f"'{search_keyword}'과(와) 일치하는 법령이나 행정규칙을 찾지 못했습니다. 단어를 짧게(예: '단열재' 또는 '에너지') 입력해 보세요.")
        else:
            st.success(f"✅ 총 {total_results}개의 관련 법령 및 행정규칙을 찾아냈습니다!")
