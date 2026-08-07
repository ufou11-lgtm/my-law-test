import streamlit as st
import requests
import xml.etree.ElementTree as ET
import re

# ==========================================
# 1. 페이지 기본 설정 및 헤더
# ==========================================
st.set_page_config(page_title="AI 건축 법령 검토 툴", page_icon="🏗️", layout="wide")

st.title("🏗️ 건축 법령 및 지자체 조례 통합 검토 툴")
st.caption("주소와 검토 키워드를 입력하면 관련 국가 법령 및 지자체 조례의 조문을 검색해 드립니다.")

# 법제처 Open API 사용자 키 (OC 값) 입력 창
# (인증키가 없는 상태에서도 가상 데이터 테스트가 가능하도록 설정했습니다.)
api_oc = st.sidebar.text_input("법제처 API OC(사용자ID) 입력", value="test", help="국가법령정보센터에서 발급받은 OC 값을 입력하세요. (기본값: test)")

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
    """
    사용자가 입력한 문장에서 지역명과 법률 검색 키워드를 추출합니다.
    예: '인천광역시 옹진군 덕적면 진리 건폐율' -> 지역: 인천광역시, 키워드: 건폐율
    """
    # 광역시/도 단위 추출
    sido_match = re.search(r'(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|경기도|강원특별자치도|충청북도|충청남도|전북특별자치도|전라남도|경상북도|경상남도|제주특별자치도)', user_text)
    sido = sido_match.group(0) if sido_match else ""
    
    # 시/군/구 단위 추출
    sugg_match = re.search(r'([가-힣]+시|[가-힣]+군|[가-힣]+구)', user_text)
    sugg = sugg_match.group(0) if sugg_match else ""

    # 검색 대상 주요 건축 키워드 목록
    keywords = ["건폐율", "용적률", "높이제한", "일조권", "주차장", "에너지절약", "용도지역", "조경", "대지안의 공지"]
    found_keywords = [kw for kw in keywords if kw in user_text]
    
    # 키워드가 특별히 지정되지 않았다면 문장 마지막 단어를 키워드로 사용
    keyword = found_keywords 0  if found_keywords else user_text.split()[-1]
    
    return sido, sugg, keyword

# ==========================================
# 3. 법제처 API 연동 함수
# ==========================================
def search_law_articles(oc, target_type, query_name, keyword):
    """
    법제처 Open API를 호출하여 법령/조례를 검색하고 키워드가 포함된 조문을 가져옵니다.
    target_type: 'law' (국가법령) 또는 'ordin' (자치법규/조례)
    """
    results = []
    
    # 1단계: 법령/조례 목록 검색 (lawSearch.do)
    search_url = f"http://www.law.go.kr/DRF/lawSearch.do?OC={oc}&target={target_type}&type=XML&query={query_name}"
    
    try:
        response = requests.get(search_url, timeout=5)
        if response.status_code != 200:
            return results
        
        root = ET.fromstring(response.content)
        
        # 검색 결과 중 첫 번째 항목의 일련번호(MST) 가져오기
        item_node = root.find('.//law') if target_type == 'law' else root.find('.//ordin')
        if item_node is None:
            return results
        
        mst = item_node.findtext('법령일련번호') if target_type == 'law' else item_node.findtext('자치법규일련번호')
        law_title = item_node.findtext('법령명한글') if target_type == 'law' else item_node.findtext('자치법규명')
        
        if not mst:
            return results
            
        # 2단계: 상세 법령 본문 및 조문 검색 (lawService.do)
        service_url = f"http://www.law.go.kr/DRF/lawService.do?OC={oc}&target={target_type}&MST={mst}&type=XML"
        detail_resp = requests.get(service_url, timeout=5)
        
        if detail_resp.status_code == 200:
            detail_root = ET.fromstring(detail_resp.content)
            
            # 조문별 탐색
            for jo in detail_root.findall('.//조문단위'):
                jo_title = jo.findtext('조제목', '')
                jo_content = jo.findtext('조내용', '')
                jo_num = jo.findtext('조문번호', '')
                
                # 조문 내용이나 제목에 키워드가 포함되어 있는지 검사
                if keyword in jo_title or keyword in jo_content:
                    # 항/호 내용 추가 수집
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
                    
    except Exception as e:
        # API 오류 발생 시 예외 처리
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
        # 1. 입력문 분석
        sido, sugg, keyword = parse_user_input(user_input)
        
        st.subheader("📌 검색 조건 분석 결과")
        col1, col2, col3 = st.columns(3)
        col1.metric("지역(시·도)", sido if sido else "전국")
        col2.metric("시·군·구", sugg if sugg else "전체")
        col3.metric("검토 핵심 키워드", keyword)
        st.divider()

        with st.spinner("법제처 API에서 관련 국가 법령 및 자치법규(조례) 조문을 검색 중입니다..."):
            all_results = []
            
            # A. 자치법규(지자체 도시계획조례 & 건축조례) 검색
            if sido:
                local_ordinance_names = [f"{sido} 도시계획조례", f"{sido} 건축조례"]
                if sugg:
                    local_ordinance_names.append(f"{sugg} 도시계획조례")
                    local_ordinance_names.append(f"{sugg} 건축조례")
                
                for ordin_name in local_ordinance_names:
                    res = search_law_articles(api_oc, "ordin", ordin_name, keyword)
                    all_results.extend(res)

            # B. 국가 주요 건축 법령 검색
            for law_name in TARGET_NATIONAL_LAWS:
                res = search_law_articles(api_oc, "law", law_name, keyword)
                all_results.extend(res)

        # 2. 검색 결과 출력
        st.subheader(f"📋 '{keyword}' 관련 법령 및 조례 검색 결과 (총 {len(all_results)}건)")
        
        if all_results:
            for item in all_results:
                with st.expander(f"📖 [{item['law_title']}] {item['article_num']} ({item['article_title']})"):
                    st.markdown(f"**조문 내용:**")
                    st.text(item['content'])
        else:
            # API 키가 'test'이거나 실제 검색 결과가 안 넘어올 경우를 대비한 대화형 예시 안내 (가상 시뮬레이션)
            st.info("💡 법제처 Open API 연동 호출 결과가 없거나 'test' 키 사용 중입니다. 아래는 시스템 예시 출력 화면입니다.")
            
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
                (이와 같이 법제처 API 연동 시 해당 조례 내용이 창에 그대로 출력됩니다.)
                """)
