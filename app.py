import streamlit as st
import requests
import xml.etree.ElementTree as ET
import re
import os  # 👈 [추가] 환경변수를 읽어오기 위한 파이썬 기본 라이브러리

# ==========================================
# 1. 페이지 기본 설정 및 헤더
# ==========================================
st.set_page_config(page_title="AI 건축 법령 검토 툴", page_icon="🏗️", layout="wide")

st.title("🏗️ 건축 법령 및 지자체 조례 통합 검토 툴")
st.caption("주소와 검토 키워드를 입력하면 관련 국가 법령 및 지자체 조례의 조문을 검색해 드립니다.")

# 👈 [수정] 구글 클라우드 환경변수(OC_KEY)에서 키를 먼저 불러오고, 없으면 'test'를 사용합니다.
default_oc_key = os.getenv("OC_KEY", "test")

# 법제처 Open API 사용자 키 (OC 값) 입력 창
# 환경변수에 등록한 실제 키가 자동으로 채워지며, 필요시 화면에서 수정할 수도 있습니다.
api_oc = st.sidebar.text_input(
    "법제처 API OC(사용자ID) 입력", 
    value=default_oc_key, 
    help="구글 클라우드 환경변수(OC_KEY)가 설정되어 있으면 자동으로 입력됩니다."
)

# 검색 대상 법령 목록 정의
TARGET_NATIONAL_LAWS = [
    "국토의 계획 및 이용에 관한 법률",
    "국토의 계획 및 이용에 관한 법률 시행령",
    "건축법",
    "건축법 시행령",
    "건축법 시행규칙",
    "건축물의 에너지절약설계기준"
]

# ==========================================
# 2. 검색어 분석 함수 (지역명 & 키워드 분리)
# ==========================================
def parse_user_input(user_text):
    sido_match = re.search(r'(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원특별자치도|충청북도|충청남도|전북특별자치도|전라남도|경상북도|경상남도|제주특별자치도)', user_text)
    sido = sido_match.group(0) if sido_match else ""
    
    sugg_match = re.search(r'([가-힣]+시|[가-힣]+군|[가-힣]+구)', user_text)
    sugg = sugg_match.group(0) if sugg_match else ""

    keywords = ["건폐율", "용적률", "높이제한", "일조권", "주차장", "에너지절약", "용도지역", "조경", "대지안의 공지"]
    found_keywords = [kw for kw in keywords if kw in user_text]
    
    keyword = found_keywords[0] if found_keywords else user_text.split()[-1]
    
    return sido, sugg, keyword

# ==========================================
# 3. 법제처 API 연동 함수
# ==========================================
def search_law_articles(oc, target_type, query_name, keyword):
    results = []
    search_url = f"http://www.law.go.kr/DRF/lawSearch.do?OC={oc}&target={target_type}&type=XML&query={query_name}"
    
    try:
        response = requests.get(search_url, timeout=5)
        if response.status_code != 200:
            return results
        
        root = ET.fromstring(response.content)
        item_node = root.find('.//law') if target_type == 'law' else root.find('.//ordin')
        if item_node is None:
            return results
        
        mst = item_node.findtext('법령일련번호') if target_type == 'law' else item_node.findtext('자치법규일련번호')
        law_title = item_node.findtext('법령명한글') if target_type == 'law' else item_node.findtext('자치법규명')
        
        if not mst:
            return results
            
        service_url = f"http://www.law.go.kr/DRF/lawService.do?OC={oc}&target={target_type}&MST={mst}&type=XML"
        detail_resp = requests.get(service_url, timeout=5)
        
        if detail_resp.status_code == 200:
            detail_root = ET.fromstring(detail_resp.content)
            
            for jo in detail_root.findall('.//조문단위'):
                jo_title = jo.findtext('조제목', '')
                jo_content = jo.findtext('조내용', '')
                jo_num = jo.findtext('조문번호', '')
                
                if keyword in jo_title or keyword in jo_content:
                    sub_contents = []
                    for hang in jo.findall('.//항'):
                        hang_content = hang.findtext('항내용', '')
                        if hang_content:
                            sub_contents.append(hang_content)
                    
                    full_text = jo_content + "\n" + "\n".join(sub_contents)
                    results.append({
                        "law_title": law_title,
                        "article_num": f"제{jo_num}조",
                        "article_title": jo_title,
                        "content": full_text
                    })
                    
    except Exception:
        pass
        
    return results

# ==========================================
# 4. 사용자 대화창(UI) 구성
# ==========================================
user_input = st.text_input(
    "검토하고 싶은 위치와 주요 항목을 입력하세요:",
    placeholder="예: 인천광역시 옹진군 덕적면 진리 건폐율",
    value="인천광역시 옹진군 덕적면 진리 건폐율"
)

if st.button("🔍 건축 법령 검토 시작", type="primary"):
    if not user_input.strip():
        st.warning("검색어를 입력해 주세요.")
    else:
        sido, sugg, keyword = parse_user_input(user_input)
        
        st.subheader("📌 검색 조건 분석 결과")
        col1, col2, col3 = st.columns(3)
        col1.metric("지역(시·도)", sido if sido else "전국")
        col2.metric("시·군·구", sugg if sugg else "전체")
        col3.metric("검토 핵심 키워드", keyword)
        st.divider()

        with st.spinner("법제처 API에서 관련 국가 법령 및 자치법규(조례) 조문을 검색 중입니다..."):
            all_results = []
            
            if sido:
                local_ordinance_names = [f"{sido} 도시계획조례", f"{sido} 건축조례"]
                if sugg:
                    local_ordinance_names.append(f"{sugg} 도시계획조례")
                    local_ordinance_names.append(f"{sugg} 건축조례")
                
                for ordin_name in local_ordinance_names:
                    res = search_law_articles(api_oc, "ordin", ordin_name, keyword)
                    all_results.extend(res)

            for law_name in TARGET_NATIONAL_LAWS:
                res = search_law_articles(api_oc, "law", law_name, keyword)
                all_results.extend(res)

        st.subheader(f"📋 '{keyword}' 관련 법령 및 조례 검색 결과 (총 {len(all_results)}건)")
        
        if all_results:
            for item in all_results:
                with st.expander(f"📖 [{item['law_title']}] {item['article_num']} ({item['article_title']})"):
                    st.markdown(f"**조문 내용:**")
                    st.text(item['content'])
        else:
            st.info("💡 법제처 Open API 연동 결과가 없거나 API 키가 올바르지 않습니다. 아래는 시스템 예시 출력 화면입니다.")
            
            st.success(f"**[예시 출력] {sido} 도시계획조례**")
            with st.expander(f"📖 [{sido if sido else '인천광역시'} 도시계획조례] 제64조 (용도지역 안에서의 건폐율)", expanded=True):
                st.write("""
                **제64조(용도지역 안에서의 건폐율)** 
                법 제77조 및 영 제84조제1항의 규정에 의하여 용도지역 안에서의 건폐율은 다음 각호와 같다.
                1. 제1종전용주거지역 : 50퍼센트 이하
                2. 제2종전용주거지역 : 50퍼센트 이하
                3. 제1종일반주거지역 : 60퍼센트 이하
                4. 제2종일반주거지역 : 60퍼센트 이하
                5. 제3종일반주거지역 : 50퍼센트 이하
                ...
                """)
