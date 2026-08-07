import os
import streamlit as st
import requests
import urllib.parse
import base64
import re

# 💡 용도지역 리스트 (사용자가 쉽게 선택할 수 있게 추가)
ZONING_AREAS = [
    "전체/해당없음", "제1종전용주거지역", "제2종전용주거지역", "제1종일반주거지역", 
    "제2종일반주거지역", "제3종일반주거지역", "준주거지역", "상업지역", 
    "전용공업지역", "일반공업지역", "준공업지역", "보전녹지지역", 
    "생산녹지지역", "자연녹지지역", "보전관리지역", "생산관리지역", 
    "계획관리지역", "농림지역", "자연환경보전지역"
]

def load_api_key():
    key = os.environ.get("OC_KEY")
    if key: return key
    try:
        return st.secrets["OC_KEY"]
    except Exception:
        return None

API_KEY = load_api_key()
if not API_KEY:
    st.error("🚨 API 키가 설정되지 않았습니다.")
    st.stop()

REQUEST_TIMEOUT = 15

st.set_page_config(page_title="프롭테크 법규 검토", page_icon="🏢", layout="wide")
st.title("🏢 스마트 법규 검토 시스템 (지역별 맞춤형)")
st.markdown("지역과 용도지역을 선택하면 해당 지자체 조례를 즉시 찾아 비교해 드립니다.")

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_api_json(url, params):
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}

@st.cache_data(show_spinner=False, ttl=1800)
def get_pdf_base64(pdf_url):
    try:
        resp = requests.get(pdf_url, timeout=10)
        if resp.status_code == 200:
            return base64.b64encode(resp.content).decode('utf-8')
    except Exception:
        pass
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
    # 항/호/목 재귀적으로 안전하게 추출
    for key in ["Ho", "호", "Hang", "항"]:
        for item in ensure_list(jo_node.get(key)):
            texts.append(safe_str(item.get("hoCntt") or item.get("호내용") or item.get("hangCntt") or item.get("항내용")))
    return "\n\n".join(texts)

def extract_jo_byl(data):
    jo_list, byl_list = [], []
    def traverse(node):
        if isinstance(node, dict):
            if "joCntt" in node or "조문내용" in node: jo_list.append(node)
            if "bylSj" in node or "별표제목" in node or "bylPdfLink" in node: byl_list.append(node)
            for v in node.values(): traverse(v)
        elif isinstance(node, list):
            for item in node: traverse(item)
    traverse(data)
    return jo_list, byl_list

# 💡 [업그레이드] 입력 폼: 지역명과 용도지역 선택 추가
with st.form(key="search_form"):
    col1, col2 = st.columns(2)
    region = col1.text_input("검토할 지역명 (예: 옹진군, 강남구)")
    zoning = col2.selectbox("용도지역 선택 (선택사항)", ZONING_AREAS)
    keyword = st.text_input("검색어 (예: 건폐율, 단열재)")
    submit_button = st.form_submit_button("🔍 맞춤 법규 분석 시작")

if submit_button:
    if not keyword:
        st.warning("검색어를 입력해주세요!")
    else:
        # 💡 [핵심 로직] 사용자 입력을 바탕으로 타겟 검색법령 동적 생성
        search_targets = []
        
        # 1. 국가 기본 법령 추가
        if "건폐" in keyword or "용적" in keyword:
            search_targets.append({"code": "law", "law_name": "국토의 계획 및 이용에 관한 법률", "label": "🏛️ 국가 법령(국토계획법)"})
        elif "단열" in keyword:
            search_targets.append({"code": "admrul", "law_name": "건축물의 에너지절약설계기준", "label": "행정규칙(에너지설계기준)"})
        else:
            search_targets.append({"code": "law", "law_name": "건축법", "label": "기본 법령(건축법)"})
            
        # 2. 지역 조례 추가
        if region:
            # 보통 조례명은 'OO시 도시계획 조례' 또는 'OO군 군계획 조례'
            ordin_name = f"{region} 도시계획 조례" if "구" in region or "시" in region else f"{region} 군계획 조례"
            search_targets.append({"code": "ordin", "law_name": ordin_name, "label": f"🏠 지자체 조례 ({region})"})

        total_found_count = 0
        
        with st.status("⚙️ **지역 맞춤 법규 분석 중...**", expanded=True) as status:
            for target in search_targets:
                code, law_name, label = target["code"], target["law_name"], target["label"]
                st.write(f"🔍 [{label}] `{law_name}` 검색 중...")
                
                list_data = fetch_api_json("https://www.law.go.kr/DRF/lawSearch.do", {"OC": API_KEY, "target": code, "type": "JSON", "query": law_name})
                items = []
                for v in list(list_data.values()): # 안전하게 목록 추출
                    if isinstance(v, (list, dict)): items.extend(ensure_list(v))

                for item in items:
                    item_name = safe_str(item.get("법령명한글") or item.get("행정규칙명") or item.get("자치법규명"))
                    if law_name.split()[0] not in item_name: continue # 이름 필터링

                    # 상세 조회
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(item.get("법령상세링크") or item.get("자치법규상세링크") or "").query)
                    detail_params = {"OC": API_KEY, "target": code, "type": "JSON"}
                    detail_params['ID'] = qs.get('MST', qs.get('ID', qs.get('ordinSeq', [''])))[0]
                    
                    detail_data = fetch_api_json("https://www.law.go.kr/DRF/lawService.do", detail_params)
                    jo_list, byl_list = extract_jo_byl(detail_data)
                    
                    # 💡 [필터링 강화] 용도지역이 선택되었다면, 조문 내용에 용도지역 이름이 들어있는 조문만 필터링!
                    found_jo = []
                    for jo in jo_list:
                        content = extract_full_jo_text(jo)
                        # 검색어(건폐율) + 선택한 용도지역명(계획관리지역)이 모두 있는 경우만 발췌
                        match_keyword = keyword in content
                        match_zoning = (zoning == "전체/해당없음") or (zoning in content)
                        
                        if match_keyword and match_zoning:
                            found_jo.append({"no": safe_str(jo.get("조문번호")), "title": safe_str(jo.get("조문제목")), "content": content})

                    if found_jo:
                        total_found_count += 1
                        with st.expander(f"🎯 [{label}] {item_name}", expanded=True):
                            for art in found_jo[:5]:
                                st.markdown(f"**제{art['no']}조({art['title']})**")
                                st.markdown(f"> {art['content']}")
                                st.divider()
