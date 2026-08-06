import streamlit as st
import requests

# -----------------------------------------------------------------------
# ⚠️ API 키는 코드에 직접 적지 않습니다.
# 1) 로컬 실행: 이 파일과 같은 폴더에 .streamlit/secrets.toml 파일을 만들고
#      OC_KEY = "여기에_본인_키"
#    라고 한 줄 적어두세요. (.gitignore에 .streamlit/secrets.toml 꼭 추가!)
# 2) Streamlit Cloud 배포: 앱 설정(Settings) > Secrets 메뉴에 같은 내용을 등록하세요.
# -----------------------------------------------------------------------
try:
    API_KEY = st.secrets["whdbswn963"]
except Exception:
    st.error("API 키가 설정되지 않았습니다. .streamlit/secrets.toml 에 OC_KEY 값을 등록해주세요.")
    st.stop()

REQUEST_TIMEOUT = 10  # 초. API가 응답 없이 멈추는 것을 방지

st.set_page_config(page_title="스마트 법규 검토 시스템", page_icon="⚖️")
st.title("⚖️ 스마트 법규 검토 시스템 (통합 검색)")
st.markdown("키워드를 입력하면 **기본 법령**뿐만 아니라 세부 기준이 담긴 **행정규칙(고시, 지침)**까지 모두 뒤져서 조문을 찾아냅니다.")
st.caption("⚠️ 참고: '단열재 두께'처럼 구체적인 수치 기준은 조문 본문이 아니라 '별표(첨부표)'에 있는 경우가 많아, "
           "본문 검색만으로는 못 찾을 수 있습니다. 그런 경우엔 원문 링크를 눌러 별표를 직접 확인해보세요.")

search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 단열재, 건축물 에너지, 주차장)")


@st.cache_data(show_spinner=False, ttl=3600)
def search_list(keyword: str, target_code: str):
    """1단계: 키워드로 법령/행정규칙 목록 검색 (결과를 1시간 캐시)"""
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {
        "OC": API_KEY,
        "target": target_code,
        "type": "JSON",
        "query": keyword,
        "search": "1",
    }
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_detail(item_id: str, target_code: str):
    """2단계: 개별 법령/행정규칙의 조문 본문 조회 (결과를 1시간 캐시)"""
    url = "https://www.law.go.kr/DRF/lawService.do"
    params = {
        "OC": API_KEY,
        "target": target_code,
        "type": "JSON",
        "ID": item_id,
    }
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


if st.button("법령 및 행정규칙 통합 검색하기"):
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        targets = [
            {"code": "law", "label": "법령", "detail_key": "Law"},
            {"code": "admrul", "label": "행정규칙", "detail_key": "Admrul"},
        ]

        total_found_count = 0

        with st.spinner(f"법령과 행정규칙에서 '{search_keyword}'(을)를 찾고 있습니다. 잠시만 기다려주세요..."):
            for t in targets:
                try:
                    data = search_list(search_keyword, t["code"])
                except Exception as e:
                    st.error(f"{t['label']} 검색 중 오류가 발생했습니다: {e}")
                    continue

                items = []
                if "LawSearch" in data:
                    if "law" in data["LawSearch"]:
                        items = data["LawSearch"]["law"]
                    elif "admrul" in data["LawSearch"]:
                        items = data["LawSearch"]["admrul"]

                if not items:
                    continue

                st.markdown(f"### 📂 관련 {t['label']} 분석 결과")

                # 상위 5개 문서만 본문을 확인 (너무 많으면 느려짐)
                for item in items[:5]:
                    item_name = item.get("법령명한글") or item.get("행정규칙명") or "이름 없음"
                    item_id = item.get("법령일련번호") or item.get("행정규칙일련번호") or ""
                    item_link = item.get("법령상세링크") or item.get("행정규칙상세링크") or ""

                    if not item_id:
                        continue

                    # ⚠️ 항목별로 try/except를 걸어서, 하나가 실패해도 나머지는 계속 진행됩니다.
                    try:
                        detail_data = fetch_detail(item_id, t["code"])
                    except Exception as e:
                        st.warning(f"'{item_name}' 상세 조회 중 오류가 발생했습니다: {e}")
                        continue

                    found_texts = []
                    detail_root = detail_data.get(t["detail_key"], {})

                    if "Jo" in detail_root:
                        jo_list = detail_root["Jo"]
                        if isinstance(jo_list, dict):
                            jo_list = [jo_list]

                        for jo in jo_list:
                            jo_content = jo.get("joCntt", "")
                            if search_keyword in jo_content:
                                found_texts.append(jo_content)

                    if found_texts:
                        total_found_count += 1
                        with st.expander(f"📌 [{t['label']}] {item_name}", expanded=True):
                            for text in found_texts:
                                highlighted = text.replace(search_keyword, f"**{search_keyword}**")
                                st.markdown(f"- {highlighted}")

                            full_link = f"https://www.law.go.kr{item_link}"
                            st.markdown(f"[➡️ 이 {t['label']} 전체 원문 보기 (별표 포함)]({full_link})")

        if total_found_count == 0:
            st.info(
                f"'{search_keyword}'(이)가 조문 본문에 포함된 법령이나 행정규칙을 찾지 못했습니다. "
                f"키워드를 조금 더 짧게 줄여보세요. (예: '단열재 두께' → '단열재')\n\n"
                f"※ 수치 기준표는 '별표'에만 있는 경우가 많으니, 검색된 문서가 있다면 원문 링크로 별표도 확인해보세요."
            )
        else:
            st.success("✅ 모든 분석이 완료되었습니다!")
