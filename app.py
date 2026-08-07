import os
import streamlit as st
import requests
import urllib.parse
import base64
import re

# ... (API_KEY 로드 부분 생략, 이전과 동일) ...
def load_api_key():
    key = os.environ.get("OC_KEY")
    if key: return key
    try: return st.secrets["OC_KEY"]
    except Exception: return None

API_KEY = load_api_key()
if not API_KEY:
    st.error("🚨 API 키 오류"); st.stop()

REQUEST_TIMEOUT = 10

st.set_page_config(page_title="스마트 법규 검토 시스템", page_icon="🏢", layout="wide")
st.title("🏢 스마트 법규 검토 시스템 (프롭테크 버전)")

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_api_json(url, params):
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200: return resp.json()
    except Exception: pass
    return {}

@st.cache_data(show_spinner=False, ttl=1800)
def get_pdf_base64(pdf_url):
    try:
        resp = requests.get(pdf_url, timeout=10)
        if resp.status_code == 200: return base64.b64encode(resp.content).decode('utf-8')
    except Exception: pass
    return None

def ensure_list(data):
    if not data: return []
    if isinstance(data, dict): return [data]
    return data

def safe_str(val):
    if not val: return ""
    if isinstance(val, str): return val
    if isinstance(val, list): return " ".join(safe_str(x) for x in val)
    return str(val)

def extract_full_jo_text(jo_node):
    texts = []
    jo_cntt = safe_str(jo_node.get("joCntt") or jo_node.get("조문내용"))
    if jo_cntt.strip(): texts.append(jo_cntt)
    # 핵심 텍스트만 추출
    return "\n\n".join(texts)

def extract_jo_byl(data):
    jo_list, byl_list = [], []
    def traverse(node):
        if isinstance(node, dict):
            if "joCntt" in node or "조문내용" in node: jo_list.append(node)
            if "bylSj" in node or "별표제목" in node or "별표명" in node or "bylPdfLink" in node: byl_list.append(node)
            for v in node.values(): traverse(v)
        elif isinstance(node, list):
            for item in node: traverse(item)
    traverse(data)
    return jo_list, byl_list

with st.form(key="search_form"):
    col1, col2 = st.columns(2)
    region = col1.text_input("지역명 (예: 옹진군)")
    keyword = col2.text_input("검색어 (예: 건폐율)")
    submit_button = st.form_submit_button("🔍 초고속 법규 분석 시작")

if submit_button:
    if not keyword: st.warning("검색어를 입력해주세요!"); st.stop()

    search_targets = []
    if any(kw in keyword for kw in ["단열", "두께"]):
        search_targets.append({"code": "admrul", "law_name": "건축물의 에너지절약설계기준", "label": "행정규칙"})
    elif "건폐" in keyword or "용적" in keyword:
        search_targets.append({"code": "law", "law_name": "국토의 계획 및 이용에 관한 법률", "label": "🏛️ 국토계획법"})
        if region: search_targets.append({"code": "ordin", "law_name": f"{region} {'군' if '군' in region else '도시'}계획 조례", "label": f"🏠 {region} 조례"})
    
    total_found_count = 0
    
    with st.status("⚙️ **최적화된 법령 조회 중...**", expanded=True) as status:
        for target in search_targets:
            code, law_name, label = target["code"], target["law_name"], target["label"]
            
            # 💡 속도 개선: 검색 결과 1페이지(기본값)만 딱 1번 가져옵니다.
            list_data = fetch_api_json("https://www.law.go.kr/DRF/lawSearch.do", {"OC": API_KEY, "target": code, "type": "JSON", "query": law_name})
            
            items = []
            for v in list(list_data.values()):
                if isinstance(v, (list, dict)): items.extend(ensure_list(v))

            # 💡 속도 개선: 모든 법령을 다 조회하지 않고, 가장 정확한 상위 2개만 골라냅니다.
            candidate_items = [i for i in items if law_name.split()[0] in safe_str(i.get("법령명한글") or i.get("자치법규명"))][:2]

            for item in candidate_items:
                item_name = safe_str(item.get("법령명한글") or item.get("행정규칙명") or item.get("자치법규명"))
                item_link = safe_str(item.get("법령상세링크") or item.get("행정규칙상세링크") or item.get("자치법규상세링크"))
                
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(item_link).query)
                detail_params = {"OC": API_KEY, "target": code, "type": "JSON", "ID": qs.get('MST', qs.get('ID', qs.get('ordinSeq', [''])))[0]}
                
                detail_data = fetch_api_json("https://www.law.go.kr/DRF/lawService.do", detail_params)
                jo_list, byl_list = extract_jo_byl(detail_data)
                
                found_jo = [j for j in jo_list if keyword in extract_full_jo_text(j)][:3] # 조문도 상위 3개만

                if found_jo or byl_list:
                    total_found_count += 1
                    with st.expander(f"🎯 [{label}] {item_name}", expanded=True):
                        for art in found_jo:
                            st.markdown(f"**제{art.get('조문번호', '')}조**")
                            st.markdown(f"> {extract_full_jo_text(art)}")
                            st.divider()
                        
                        # 별표 PDF 처리
                        for byl in byl_list[:2]: # 별표도 상위 2개만
                            pdf_url = f"https://www.law.go.kr{byl.get('bylPdfLink', '')}"
                            st.markdown(f"📎 **{byl.get('별표제목', '관련 별표')}**")
                            st.markdown(f"👉 [PDF 열기]({pdf_url})")

        if total_found_count == 0: status.update(label="❌ 결과를 찾지 못했습니다.", state="error")
        else: status.update(label="✅ 분석 완료!", state="complete")
