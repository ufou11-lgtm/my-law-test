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

st.set_page_config(page_title="스마트 법규 검토 시스템", page_icon="⚖️", layout="wide")
st.title("⚖️ 스마트 법규 검토 시스템 (실무형 통합 검색)")
st.markdown("건축 용어(**건폐율, 용적률, 단열재의 두께** 등)를 입력하고 **엔터(Enter)**를 누르세요. 연계된 법령과 별표 PDF를 한 번에 찾아 띄워줍니다.")

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

# 💡 [핵심 해결 로직] 조문 안쪽에 숨어있는 '항(Hang)', '호(Ho)', '목(Mok)' 데이터를 모조리 긁어오는 함수
def extract_full_jo_text(jo_node):
    texts = []
    
    # 1. 기본 조문 내용 (껍데기)
    jo_cntt = jo_node.get("joCntt") or jo_node.get("조문내용") or ""
    if jo_cntt: 
        texts.append(jo_cntt)

    # 2. 직계 호(Ho)와 목(Mok) 추출 (항이 생략되고 바로 호가 나오는 법령 대비)
    for ho in ensure_list(jo_node.get("Ho") or jo_node.get("호") or []):
        ho_cntt = ho.get("hoCntt") or ho.get("호내용") or ""
        if ho_cntt: texts.append(ho_cntt)
        for mok in ensure_list(ho.get("Mok") or ho.get("목") or []):
            mok_cntt = mok.get("mokCntt") or mok.get("목내용") or ""
            if mok_cntt: texts.append(mok_cntt)

    # 3. 항(Hang), 그리고 그 안의 호(Ho), 목(Mok) 추출
    for hang in ensure_list(jo_node.get("Hang") or jo_node.get("항") or []):
        hang_cntt = hang.get("hangCntt") or hang.get("항내용") or ""
        if hang_cntt: texts.append(hang_cntt)
        
        for ho in ensure_list(hang.get("Ho") or hang.get("호") or []):
            ho_cntt = ho.get("hoCntt") or ho.get("호내용") or ""
            if ho_cntt: texts.append(ho_cntt)
            
            for mok in ensure_list(ho.get("Mok") or ho.get("목") or []):
                mok_cntt = mok.get("mokCntt") or mok.get("목내용") or ""
                if mok_cntt: texts.append(mok_cntt)

    # 추출한 모든 텍스트를 줄바꿈으로 예쁘게 이어 붙입니다.
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

with st.form(key="search_form"):
    search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 건폐율, 단열재의 두께)")
    submit_button = st.form_submit_button("🔍 법 조문 및 별표 PDF 바로 띄우기")

if submit_button:
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        raw_tokens = search_keyword.split()
        clean_tokens = [re.sub(r'(의|를|을|은|는|이|가)$', '', tok) for tok in raw_tokens]
        clean_tokens = [tok for tok in clean_tokens if len(tok) >= 2]
        if not clean_tokens:
            clean_tokens = raw_tokens

        search_targets = []
        if any(kw in search_keyword for kw in ["단열", "두께", "단열재"]):
            search_targets.append({"code": "admrul", "law_name": "건축물의 에너지절약설계기준", "label": "행정규칙(고시)"})
        elif "건폐" in search_keyword or "용적" in search_keyword:
            search_targets.append({"code": "law", "law_name": "건축법", "label": "기본 법령"})
            search_targets.append({"code": "law", "law_name": "국토의 계획 및 이용에 관한 법률", "label": "🔗 연계 법령(국토계획법)"})
        elif "주차" in search_keyword:
            search_targets.append({"code": "law", "law_name": "주차장법", "label": "법령"})
        else:
            search_targets.append({"code": "admrul", "law_name": clean_tokens[0], "label": "행정규칙"})
            search_targets.append({"code": "law", "law_name": "건축법", "label": "법령"})

        total_found_count = 0
        
        with st.status("⚙️ **가장 정확한 법령 및 별표 데이터 정밀 분석 중...**", expanded=True) as status:
            st.write(f"▶️ 스마트 타겟팅 적용 완료 | 추출된 키워드: `{clean_tokens}`")
            
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
                    item_name = item.get("법령명한글") or item.get("행정규칙명") or "이름 없음"
                    item_link = item.get("법령상세링크") or item.get("행정규칙상세링크")
                    
                    if not item_link:
                        continue

                    if law_name.replace(" ", "") not in item_name.replace(" ", ""):
                        continue

                    parsed = urllib.parse.urlparse(item_link)
                    qs = urllib.parse.parse_qs(parsed.query)
                    
                    detail_params = {"OC": API_KEY, "target": code, "type": "JSON"}
                    if 'MST' in qs: detail_params['MST'] = qs['MST'][0]
                    if 'ID' in qs: detail_params['ID'] = qs['ID'][0]
                    if 'admRulSeq' in qs: detail_params['ID'] = qs['admRulSeq'][0]
                    
                    detail_data = fetch_api_json("https://www.law.go.kr/DRF/lawService.do", detail_params)
                    if not detail_data or not isinstance(detail_data, dict):
                        continue
                        
                    jo_list, byl_list = extract_jo_byl(detail_data)
                    
                    found_articles = []
                    byeonpyo_matches = []

                    for jo in jo_list:
                        jo_no = str(jo.get("joNo") or jo.get("조문번호") or "")
                        jo_title = str(jo.get("joSj") or jo.get("조문제목") or "")
                        
                        # 💡 새로 만든 함수로 숨겨진 모든 항, 호, 목의 텍스트를 긁어옵니다.
                        jo_content = extract_full_jo_text(jo)
                        
                        text_to_search = jo_title + " " + jo_content
                        if sum(1 for tok in clean_tokens if tok in text_to_search) >= len(clean_tokens) * 0.5:
                            found_articles.append({
                                "no": jo_no,
                                "title": jo_title,
                                "content": jo_content
                            })

                    for byl in byl_list:
                        title = str(byl.get("bylSj") or byl.get("별표제목") or byl.get("별표명") or "")
                        
                        is_match = False
                        if any(kw in search_keyword for kw in ["단열", "두께"]):
                            is_match = any(tok in title for tok in ["단열재", "두께"])
                        else:
                            is_match = all(tok in title for tok in clean_tokens)

                        if is_match:
                            pdf_path = byl.get("bylPdfLink") or byl.get("별표서식PDF파일링크") or ""
                            hwp_path = byl.get("bylHwpLink") or byl.get("별표서식파일링크") or ""
                            
                            byeonpyo_matches.append({
                                "title": title,
                                "pdf_url": f"https://www.law.go.kr{pdf_path}" if pdf_path else None,
                                "hwp_url": f"https://www.law.go.kr{hwp_path}" if hwp_path else None
                            })

                    if found_articles or byeonpyo_matches:
                        total_found_count += 1
                        
                        with st.container(): 
                            with st.expander(f"🎯 [{label}] {item_name} (결과 열기)", expanded=True):
                                
                                if found_articles:
                                    st.markdown("### 📜 관련 법 조문")
                                    for art in found_articles[:7]: 
                                        st.markdown(f"**제{art['no']}조({art['title']})**")
                                        
                                        # 💡 여러 줄로 된 텍스트(항/호/목) 각각에 마크다운 인용구(>) 블록 적용
                                        highlighted = art['content']
                                        for token in clean_tokens:
                                            highlighted = highlighted.replace(token, f"**<span style='color:#e63946; background-color:#f8edeb;'>{token}</span>**")
                                        
                                        formatted_lines = "\n".join([f"> {line}" for line in highlighted.split("\n") if line.strip()])
                                        st.markdown(formatted_lines, unsafe_allow_html=True)
                                        st.divider()

                                if byeonpyo_matches:
                                    st.markdown("### 📎 관련 별표 및 첨부파일")
                                    for bp in byeonpyo_matches:
                                        st.markdown(f"**{bp['title']}**")
                                        
                                        if bp['pdf_url']:
                                            with st.spinner("PDF 문서를 화면에 불러오는 중입니다..."):
                                                pdf_b64 = get_pdf_base64(bp['pdf_url'])
                                                if pdf_b64:
                                                    st.markdown(
                                                        f'<iframe src="data:application/pdf;base64,{pdf_b64}" width="100%" height="700px" type="application/pdf"></iframe>',
                                                        unsafe_allow_html=True
                                                    )
                                                else:
                                                    st.markdown(f"👉 [PDF 파일 다운로드 링크]({bp['pdf_url']})")
                                        
                                        if bp['hwp_url']:
                                            st.markdown(f"🔗 [HWP 파일 다운로드]({bp['hwp_url']})")
                                        st.write("") 

            if total_found_count > 0:
                status.update(label=f"✅ 분석 완료! 총 {total_found_count}개의 정확한 문서를 찾았습니다.", state="complete", expanded=False)
            else:
                status.update(label="❌ 일치하는 문서를 찾지 못했습니다.", state="error", expanded=True)

        if total_found_count == 0:
            st.info("조건에 맞는 결과가 없습니다. 키워드를 한 단어로 줄여서 검색해 보세요.")
        else:
            st.toast('성공적으로 불러왔습니다!', icon='🎉')
