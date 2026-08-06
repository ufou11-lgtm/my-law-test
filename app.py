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
st.title("⚖️ 스마트 법규 검토 시스템 (통합 검색)")
st.markdown("키워드를 입력하면 **기본 법령**뿐만 아니라 세부 기준이 담긴 **행정규칙(고시, 지침)**까지 모두 뒤져서 조문을 찾아냅니다.")
st.caption("⚠️ 참고: '단열재 두께'처럼 구체적인 수치 기준은 조문 본문이 아니라 '별표(첨부표)'에 있는 경우가 많아, "
           "본문 검색만으로는 못 찾을 수 있습니다. 그런 경우엔 원문 링크를 눌러 별표를 직접 확인해보세요.")

search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 단열재, 건축물 에너지, 주차장)")
show_debug = st.checkbox(
    "🔧 원본 응답 구조 보기 (별표 필드 이름을 확인하고 싶을 때 체크)",
    help="법제처 API가 실제로 어떤 이름으로 별표 정보를 주는지 확인하는 용도입니다.",
)

@st.cache_data(show_spinner=False, ttl=3600)
def search_list(keyword: str, target_code: str):
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {
        "OC": API_KEY,
        "target": target_code,
        "type": "JSON",
        "query": keyword,
        "search": "2",  # 본문 내용까지 포함해서 검색
    }
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_detail(item_id: str, target_code: str, link_url: str = ""):
    url = "https://www.law.go.kr/DRF/lawService.do"
    
    # 1차 시도: 기본 일련번호(ID)로 요청
    params = {
        "OC": API_KEY,
        "target": target_code,
        "type": "JSON",
        "ID": item_id,
    }
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    
    # 만약 "일치하는 법령이 없습니다" 에러가 나고 링크가 있다면, 링크 안의 MST 번호를 추출해서 재시도
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

        if keyword in title or any(tok in title for tok in tokens):
            pdf_path = item.get("별표서식PDF파일링크")
            hwp_path = item.get("별표서식파일링크")
            results.append({
                "title": title,
                "pdf_url": f"https://www.law.go.kr{pdf_path}" if pdf_path else None,
                "hwp_url": f"https://www.law.go.kr{hwp_path}" if hwp_path else None,
            })

    return results

def hide_key(text: str) -> str:
    if API_KEY:
        text = text.replace(API_KEY, "********")
    return text

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

                st.markdown(f"### 📂 관련 {t['label']} 분석 결과")

                for item in items[:5]:
                    item_name = item.get("법령명한글") or item.get("행정규칙명") or "이름 없음"
                    item_id = item.get("법령일련번호") or item.get("행정규칙일련번호") or ""
                    item_link = item.get("법령상세링크") or item.get("행정규칙상세링크") or ""

                    if not item_id:
                        continue

                    try:
                        detail_data = fetch_detail(item_id, t["code"], item_link)
                    except Exception as e:
                        st.warning(f"'{item_name}' 상세 조회 중 오류가 발생했습니다: {hide_key(str(e))}")
                        continue

                    found_texts = []
                    detail_root = detail_data.get(t["detail_key"], {})

                    if show_debug:
                        with st.expander(f"🔧 [디버그] {item_name} 원본 응답 구조", expanded=False):
                            st.json(detail_data)

                    # API가 에러 문자열을 보낸 경우 건너뜁니다.
                    if isinstance(detail_root, str):
                        continue

                    if "Jo" in detail_root:
                        jo_list = detail_root["Jo"]
                        if isinstance(jo_list, dict):
                            jo_list = [jo_list]

                        for jo in jo_list:
                            jo_content = jo.get("joCntt", "")
                            if search_keyword in jo_content:
                                found_texts.append(jo_content)

                    byeonpyo_matches = find_byeonpyo(detail_root, search_keyword)

                    if found_texts or byeonpyo_matches:
                        total_found_count += 1
                        with st.expander(f"📌 [{t['label']}] {item_name}", expanded=True):
                            for text in found_texts:
                                highlighted = text.replace(search_keyword, f"**{search_keyword}**")
                                st.markdown(f"- {highlighted}")

                            if byeonpyo_matches:
                                st.markdown("**📎 관련 별표(첨부표)**")
                                for bp in byeonpyo_matches:
                                    file_url = bp["pdf_url"] or bp["hwp_url"]
                                    file_type = "PDF" if bp["pdf_url"] else "HWP"
                                    if file_url:
                                        st.markdown(f"- {bp['title']} — [{file_type} 다운로드]({file_url})")
                                    else:
                                        st.markdown(f"- {bp['title']} (다운로드 링크 없음)")

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
