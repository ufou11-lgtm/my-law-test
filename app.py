import os
import streamlit as st
import requests

# -----------------------------------------------------------------------
# ⚠️ API 키는 코드에 직접 적지 않습니다.
# "OC_KEY"는 이름표(key)이고, 실제 발급받은 키 값은 아래 두 곳 중
# 한 곳에 값으로만 넣어두면 됩니다. 이름표 자리에 실제 키 값을 넣지 마세요!
#
# 1) Google Cloud Run 배포: Cloud Run 콘솔 > 서비스 편집 및 새 버전 배포 >
#    "변수 및 보안 비밀" 탭 > 환경 변수 추가
#      이름: OC_KEY   값: 실제_발급받은_API_키
# 2) 로컬 실행: 이 파일과 같은 폴더에 .streamlit/secrets.toml 파일을 만들고
#      OC_KEY = "실제_발급받은_API_키"
#    라고 한 줄 적어두세요. (.gitignore에 .streamlit/secrets.toml 꼭 추가!)
# -----------------------------------------------------------------------
def load_api_key():
    # 1순위: 환경변수 (Cloud Run 등 서버 배포 환경)
    key = os.environ.get("OC_KEY")
    if key:
        return key
    # 2순위: secrets.toml (로컬 개발 환경)
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

REQUEST_TIMEOUT = 10  # 초. API가 응답 없이 멈추는 것을 방지

st.set_page_config(page_title="스마트 법규 검토 시스템", page_icon="⚖️")
st.title("⚖️ 스마트 법규 검토 시스템 (통합 검색)")
st.markdown("키워드를 입력하면 **기본 법령**뿐만 아니라 세부 기준이 담긴 **행정규칙(고시, 지침)**까지 모두 뒤져서 조문을 찾아냅니다.")
st.caption("⚠️ 참고: '단열재 두께'처럼 구체적인 수치 기준은 조문 본문이 아니라 '별표(첨부표)'에 있는 경우가 많아, "
           "본문 검색만으로는 못 찾을 수 있습니다. 그런 경우엔 원문 링크를 눌러 별표를 직접 확인해보세요.")

search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 단열재, 건축물 에너지, 주차장)")
show_debug = st.checkbox(
    "🔧 원본 응답 구조 보기 (별표 필드 이름을 확인하고 싶을 때 체크)",
    help="법제처 API가 실제로 어떤 이름으로 별표 정보를 주는지 확인하는 용도입니다. "
         "평소 검색할 땐 체크하지 않아도 됩니다.",
)


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


def find_byeonpyo(detail_root: dict, keyword: str):
    """
    상세조회 결과(detail_root)에서 별표 블록을 찾아, 제목이 검색어와
    관련있는 별표만 골라 PDF/HWP 다운로드 링크와 함께 돌려줍니다.

    ⚠️ 법제처 API의 실제 JSON 필드 이름이 다를 수 있습니다.
    화면에서 '원본 응답 구조 보기'를 체크해 실제 키 이름을 확인한 뒤,
    아래 byeonpyo_candidates / title_keys 목록을 맞는 이름으로
    바꿔주시면 정확도가 올라갑니다.
    """
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

    # 검색어를 단어 단위로 쪼개서, 그중 하나라도 별표 제목에 포함되면 매칭
    # (예: "단열재 두께"로 검색해도 별표 제목이 "...단열재의 두께..."면 잡히도록)
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

                    if show_debug:
                        with st.expander(f"🔧 [디버그] {item_name} 원본 응답 구조", expanded=False):
                            st.json(detail_data)

                    if "Jo" in detail_root:
                        jo_list = detail_root["Jo"]
                        if isinstance(jo_list, dict):
                            jo_list = [jo_list]

                        for jo in jo_list:
                            jo_content = jo.get("joCntt", "")
                            if search_keyword in jo_content:
                                found_texts.append(jo_content)

                    # 조문 본문뿐 아니라, 별표(첨부표) 제목도 함께 확인
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
