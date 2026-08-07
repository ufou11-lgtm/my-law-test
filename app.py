import os
import streamlit as st
import requests
import urllib.parse
import base64
import re

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

st.set_page_config(page_title="스마트 법규 검토 시스템 (프롭테크 버전)", page_icon="🏢", layout="wide")
st.title("🏢 스마트 법규 검토 시스템 (지역 조례 연동)")
st.markdown("건축 용어와 **지역명(예: 옹진군 건폐율, 서울시 용적률)**을 함께 입력해보세요. 국가 법령과 해당 지자체의 조례를 동시에 찾아줍니다.")

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

    for ho in ensure_list(jo_node.get("Ho") or jo_node.get("호") or []):
        ho_cntt = safe_str(ho.get("hoCntt") or ho.get("호내용"))
        if ho_cntt.strip(): texts.append(ho_cntt)
        for mok in ensure_list(ho.get("Mok") or ho.get("목") or []):
            mok_cntt = safe_str(mok.get("mokCntt") or mok.get("목내용"))
            if mok_cntt.strip(): texts.append(mok_cntt)

    for hang in ensure_list(jo_node.get("Hang") or jo_node.get("항") or []):
        hang_cntt = safe_str(hang.get("hangCntt") or hang.get("항내용"))
        if hang_cntt.strip(): texts.append(hang_cntt)
        for ho in ensure_list(hang.get("Ho") or hang.get("호") or []):
            ho_cntt = safe_str(ho.get("hoCntt") or ho.get("호내용"))
            if ho_cntt.strip(): texts.append(ho_cntt)
            for mok in ensure_list(ho.get("Mok") or ho.get("목") or []):
                mok_cntt = safe_str(mok.get("mokCntt") or mok.get("목내용"))
                if mok_cntt.strip(): texts.append(mok_cntt)
    return "\n\n".join(texts)

def extract_jo_byl(data):
    jo_list = []
    byl_list = []
    def traverse(node):
        if isinstance(node, dict):
            if "joCntt" in node or "조문내용" in node:
                jo_list.append(node)
            if "bylSj" in node or "별표제목" in node or "별표명" in node or "bylPdfLink" in node:
                byl_list.append(node)
            for v in node.values():
                traverse(v)
        elif isinstance(node, list):
            for item in node:
                traverse(item)
    traverse(data)
    return jo_list, byl_list

# 💡 [핵심 기능] 사용자가 입력한 검색어에서 '지역명(지자체)'을 똑똑하게 뽑아내는 함수
def extract_region_name(keyword):
    # '구, 군, 시, 도' 등으로 끝나는 단어를 찾습니다. (예: 인천광역시, 옹진군, 강남구)
    match = re.search(r'([가-힣]+(시|군|구|도))', keyword)
    if match:
        return match.group(1)
    return None

with st.form(key="search_form"):
    search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 옹진군 건폐율, 서울시 용적률)")
    submit_button = st.form_submit_button("🔍 지역 조례 및 국가 법령 통합 검색")

if submit_button:
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        raw_tokens = search_keyword.split()
        clean_tokens = [re.sub(r'(의|를|을|은|는|이|가)$', '', tok) for tok in raw_tokens]
        clean_tokens = [tok for tok in clean_tokens if len(tok) >= 2]
        if not clean_tokens:
            clean_tokens = raw_tokens

        # 지역명 추출 시도
        region_name = extract_region_name(search_keyword)

        search_targets = []
        
        # 검색어 분기 처리
        if any(kw in search_keyword for kw in ["단열", "두께", "단열재"]):
            search_targets.append({"code": "admrul", "law_name": "건축물의 에너지절약설계기준", "label": "행정규칙(고시)"})
            
        elif "건폐" in search_keyword or "용적" in search_keyword:
            # 1. 국가 법령 (기본)
            search_targets.append({"code": "law", "law_name": "국토의 계획 및 이용에 관한 법률", "label": "🏛️ 국가 법령(국토계획법)"})
            
            # 2. 지역명이 있으면 자치법규(조례) 추가 타겟팅!
            if region_name:
                if "군" in region_name:
                    ordinance_name = f"{region_name} 군계획 조례"
                else:
                    ordinance_name = f"{region_name} 도시계획 조례"
                
                # 'ordin' 코드는 지자체 조례를 검색하는 숨겨진 파라미터입니다.
                search_targets.append({"code": "ordin", "law_name": ordinance_name, "label": f"🏠 지자체 조례({region_name})"})
            else:
                search_targets.append({"code": "law", "law_name": "건축법", "label": "기본 법령(건축법)"})
                
        elif "주차" in search_keyword:
            search_targets.append({"code": "law", "law_name": "주차장법", "label": "법령"})
            if region_name:
                search_targets.append({"code": "ordin", "law_name": f"{region_name} 주차장 조례", "label": f"🏠 지자체 조례({region_name})"})
        else:
            search_targets.append({"code": "law", "law_name": "건축법", "label": "법령"})

        total_found_count = 0
        
        with st.status("⚙️ **국가 법령 및 지자체 조례 동시 분석 중...**", expanded=True) as status:
            st.write(f"▶️ 타겟팅 완료 | 핵심 키워드: `{clean_tokens}` | 감지된 지역: `{region_name if region_name else '없음'}`")
            
            for target in search_targets:
                code = target["code"]
                law_name = target["law_name"]
                label = target["label"]
                
                st.write(f"🔍 [{label}] `{law_name}` 데이터베이스 조회 중...")
                
                list_params = {"OC": API_KEY, "target": code, "type": "JSON", "query": law_name}
                list_data = fetch_api_json("https://www.law.go.kr/DRF/lawSearch.do", list_params)
                
                if not list_data or not isinstance(list_data, dict):
                    continue
                
                search_root = list(list_data.values())[0] if list_data.values() else {}
                items = []
                for k, v in search_root.items():
                    if isinstance(v, (list, dict)):
                        items.extend(ensure_list(v))

                for item in items:
                    # 조례(ordin)의 경우 키 이름이 조금 다릅니다. (자치법규명, 자치법규상세링크)
                    item_name = safe_str(item.get("법령명한글") or item.get("행정규칙명") or item.get("자치법규명") or "이름 없음")
                    item_link = safe_str(item.get("법령상세링크") or item.get("행정규칙상세링크") or item.get("자치법규상세링크"))
                    
                    if not item_link:
                        continue

                    # 이름 필터링 (너무 엉뚱한 조례가 나오는 것 방지)
                    search_law_clean = law_name.replace(" ", "")
                    item_name_clean = item_name.replace(" ", "")
                    if code == "ordin" and region_name not in item_name_clean:
                        continue
                    elif code != "ordin" and search_law_clean not in item_name_clean:
                        continue

                    parsed = urllib.parse.urlparse(item_link)
                    qs = urllib.parse.parse_qs(parsed.query)
                    
                    detail_params = {"OC": API_KEY, "target": code, "type": "JSON"}
                    if 'MST' in qs: detail_params['MST'] = qs['MST'][0]
                    if 'ID' in qs: detail_params['ID'] = qs['ID'][0]
                    if 'admRulSeq' in qs: detail_params['ID'] = qs['admRulSeq'][0]
                    # 자치법규 일련번호 파라미터 대응
                    if 'ordinSeq' in qs: detail_params['ID'] = qs['ordinSeq'][0]
                    
                    detail_data = fetch_api_json("https://www.law.go.kr/DRF/lawService.do", detail_params)
                    if not detail_data or not isinstance(detail_data, dict):
                        continue
                        
                    jo_list, byl_list = extract_jo_byl(detail_data)
                    
                    found_articles = []

                    for jo in jo_list:
                        jo_no = safe_str(jo.get("joNo") or jo.get("조문번호") or "")
                        jo_title = safe_str(jo.get("joSj") or jo.get("조문제목") or "")
                        
                        raw_content = extract_full_jo_text(jo)
                        chunks = re.split(r'(?=제\d+조(?:의\d+)?\s*\()', raw_content)
                        
                        for chunk in chunks:
                            chunk = chunk.strip()
                            if not chunk: continue
                            
                            text_to_search = jo_title + " " + chunk
                            
                            # '건폐' 또는 '용적' 검색 시, 조문 제목이나 내용에 해당 단어가 있으면 발췌
                            is_match = False
                            if "건폐" in search_keyword and "건폐" in text_to_search: is_match = True
                            elif "용적" in search_keyword and "용적" in text_to_search: is_match = True
                            elif sum(1 for tok in clean_tokens if tok in text_to_search) >= len(clean_tokens) * 0.5: is_match = True

                            if is_match:
                                m = re.match(r'(제\d+조(?:의\d+)?)\s*\((.*?)\)(.*)', chunk, re.DOTALL)
                                if m:
                                    chunk_no = m.group(1).replace("제", "").replace("조", "")
                                    chunk_title = m.group(2).strip()
                                    chunk_content = m.group(3).strip()
                                else:
                                    chunk_no = jo_no if jo_no else "-"
                                    chunk_title = jo_title if jo_title else "관련 조문 내용"
                                    chunk_content = chunk
                                
                                if not any(a['title'] == chunk_title and a['content'] == chunk_content for a in found_articles):
                                    found_articles.append({
                                        "no": chunk_no,
                                        "title": chunk_title,
                                        "content": chunk_content
                                    })

                    if found_articles:
                        total_found_count += 1
                        
                        with st.container(): 
                            # 지자체 조례는 특별히 색상을 다르게 표기하여 눈에 띄게 합니다.
                            expander_title = f"🎯 [{label}] {item_name} (결과 열기)"
                            with st.expander(expander_title, expanded=True):
                                st.markdown("### 📜 관련 법 조문 발췌")
                                for art in found_articles[:7]: 
                                    if art['no'] and art['no'] != "-":
                                        st.markdown(f"**제{art['no']}조({art['title']})**")
                                    else:
                                        st.markdown(f"**{art['title']}**")
                                        
                                    highlighted = art['content']
                                    # 강조 키워드 (건폐, 용적 등)
                                    highlight_words = ["건폐율", "용적률", "건폐", "용적"] + clean_tokens
                                    for token in set(highlight_words):
                                        if token in highlighted:
                                            highlighted = highlighted.replace(token, f"**<span style='color:#0056b3; background-color:#e6f2ff;'>{token}</span>**")
                                    
                                    formatted_lines = "\n".join([f"> {line}" for line in highlighted.split("\n") if line.strip()])
                                    st.markdown(formatted_lines, unsafe_allow_html=True)
                                    st.divider()
                                
                                full_link = f"https://www.law.go.kr{item_link}" if item_link else "https://www.law.go.kr"
                                st.markdown(f"[➡️ 원문 전체 페이지 보기]({full_link})")

            if total_found_count > 0:
                status.update(label=f"✅ 분석 완료! 국가 법령과 지자체 조례를 성공적으로 비교했습니다.", state="complete", expanded=False)
            else:
                status.update(label="❌ 일치하는 문서를 찾지 못했습니다.", state="error", expanded=True)

        if total_found_count == 0:
            st.info("조건에 맞는 결과가 없습니다. 지역명과 키워드를 다시 확인해 보세요. (예: 옹진군 건폐율)")
        else:
            st.toast('지역 조례 매칭 완료!', icon='🎯')
