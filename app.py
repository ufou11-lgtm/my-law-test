import streamlit as st
import requests

# 👉 여기에 발급받으신 JSON 전용 API 키를 입력하세요.
# 따옴표 안에 키 값만 넣으시면 됩니다.
API_KEY = "whdbswn963"

# 웹사이트의 기본 탭 이름과 아이콘 설정
st.set_page_config(page_title="법규 검토 시스템", page_icon="⚖️")

# 화면 제목과 설명
st.title("⚖️ 법규 검토 시스템")
st.markdown("키워드를 입력하면 국가법령정보센터에서 관련 법규를 찾아 보여줍니다.")

# 1. 검색어 입력칸 만들기
search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 개인정보, 건축, 도로교통)")

# 2. 검색 버튼이 눌렸을 때의 동작
if st.button("법령 검색하기"):
    
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    elif API_KEY == "whdbswn963":
        st.error("코드 상단의 API_KEY 변수에 발급받은 API 키를 넣어주세요.")
    else:
        # 3. 로딩 애니메이션 (돌아가는 동그라미) 보여주기
        with st.spinner("국가법령정보센터에서 데이터를 가져오는 중입니다..."):
            
            # 4. API에 보낼 주소와 조건(파라미터) 설정
            url = "https://www.law.go.kr/DRF/lawSearch.do"
            params = {
                "OC": API_KEY,           # 내 API 키
                "target": "law",         # 대상: 법령
                "type": "JSON",          # 결과 형식: JSON (받으신 형식)
                "query": search_keyword  # 사용자가 입력한 검색어
            }

            try:
                # API 서버에 요청(Request) 보내기
                response = requests.get(url, params=params)
                
                # 5. 정상적으로 응답(200)이 왔을 경우 JSON 데이터 풀기
                if response.status_code == 200:
                    data = response.json()
                    
                    # JSON 구조에서 'LawSearch' 안의 'law' 목록 찾기
                    if "LawSearch" in data and "law" in data["LawSearch"]:
                        law_list = data["LawSearch"]["law"]
                        
                        st.success(f"총 {len(law_list)}건의 법령이 검색되었습니다!")
                        
                        # 6. 검색된 법령 개수만큼 반복하며 화면에 보여주기
                        for law in law_list:
                            # 딕셔너리에서 필요한 정보만 쏙쏙 뽑아오기
                            law_name = law.get("법령명한글", "이름 없음")
                            enforcement_date = law.get("시행일자", "알 수 없음")
                            law_link = law.get("법령상세링크", "")
                            
                            # 클릭하면 열리는 박스(expander) 형태로 깔끔하게 표시
                            with st.expander(f"📌 {law_name}"):
                                st.write(f"**시행일자:** {enforcement_date}")
                                st.write(f"**법령 일련번호:** {law.get('법령일련번호', '정보 없음')}")
                                
                                # 원문 상세 링크가 있다면 클릭할 수 있게 버튼/링크 제공
                                if law_link:
                                    full_link = f"https://www.law.go.kr{law_link}"
                                    st.markdown(f"[➡️ 국가법령정보센터에서 원문 전체 보기]({full_link})")
                    else:
                        st.info("검색된 법령이 없습니다. 다른 키워드로 검색해보세요.")
                else:
                    st.error("API 호출에 실패했습니다. (국가법령정보센터 서버 문제일 수 있습니다.)")
            
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
