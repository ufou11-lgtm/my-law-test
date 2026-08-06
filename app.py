import streamlit as st
import requests

API_KEY = "whdbswn963"

st.set_page_config(page_title="스마트 법규 검토 시스템", page_icon="⚖️")
st.title("⚖️ 스마트 법규 검토 시스템 (통합 검색)")
st.markdown("키워드를 입력하면 **기본 법령**뿐만 아니라 세부 기준이 담긴 **행정규칙(고시, 지침)**까지 모두 뒤져서 조문을 찾아냅니다.")

search_keyword = st.text_input("검색할 키워드를 입력하세요 (예: 단열재, 건축물 에너지, 주차장)")

if st.button("법령 및 행정규칙 통합 검색하기"):
    if not search_keyword:
        st.warning("검색어를 먼저 입력해주세요!")
    else:
        # 로딩 메시지
        with st.spinner(f"법령과 행정규칙에서 '{search_keyword}'(을)를 찾고 있습니다. 잠시만 기다려주세요..."):
            
            # 검색할 대상: law(법령), admrul(행정규칙) 두 가지를 번갈아 검색합니다.
            targets = [
                {"code": "law", "label": "법령", "detail_key": "Law"},
                {"code": "admrul", "label": "행정규칙", "detail_key": "Admrul"}
            ]
            
            total_found_count = 0
            
            for t in targets:
                # 👉 [핵심] 바로 이 줄이 지워졌거나 띄어쓰기가 틀어져서 났던 에러입니다!
                search_url = "https://www.law.go.kr/DRF/lawSearch.do"
                
                search_params = {
                    "OC": API_KEY,
                    "target": t["code"],
                    "type": "JSON",
                    "query": search_keyword,
                    "search": "1"  # 본문 검색 마법의 옵션
                }
                
                try:
                    response = requests.get(search_url, params=search_params)
                    if response.status_code == 200:
                        data = response.json()
                        
                        # API 응답에서 목록 가져오기 (법령과 행정규칙의 폴더 이름이 다름을 대비)
                        items = []
                        if "LawSearch" in data:
                            if "law" in data["LawSearch"]:
                                items = data["LawSearch"]["law"]
                            elif "admrul" in data["LawSearch"]:
                                items = data["LawSearch"]["admrul"]
                                
                        if items:
                            st.markdown(f"### 📂 관련 {t['label']} 분석 결과")
                            
                            # 너무 많으면 느려지므로 최신순 상위 5개 문서만 본문을 뒤집니다.
                            for item in items[:5]:
                                # 법령과 행정규칙의 이름표가 조금씩 달라서 모두 대응할 수 있게 설정
                                item_name = item.get("법령명한글") or item.get("행정규칙명") or "이름 없음"
                                item_id = item.get("법령일련번호") or item.get("행정규칙일련번호") or ""
                                item_link = item.get("법령상세링크") or item.get("행정규칙상세링크") or ""
                                
                                if item_id:
                                    # 2단계: 본문(조문) 데이터 요청
                                    detail_url = "https://www.law.go.kr/DRF/lawService.do"
                                    detail_params = {
                                        "OC": API_KEY,
                                        "target": t["code"],
                                        "type": "JSON",
                                        "ID": item_id
                                    }
                                    
                                    detail_resp = requests.get(detail_url, params=detail_params)
                                    if detail_resp.status_code == 200:
                                        detail_data = detail_resp.json()
                                        
                                        found_texts = []
                                        
                                        # 본문 구조 확인 (Law 또는 Admrul)
                                        detail_root = detail_data.get(t["detail_key"], {})
                                        
                                        # 조문(Jo)에서 내용 추출
                                        if "Jo" in detail_root:
                                            jo_list = detail_root["Jo"]
                                            # 데이터가 1개일 때와 여러 개일 때의 오류 방지
                                            if isinstance(jo_list, dict):
                                                jo_list = [jo_list]
                                                
                                            for jo in jo_list:
                                                jo_content = jo.get("joCntt", "")
                                                if search_keyword in jo_content:
                                                    found_texts.append(jo_content)
                                        
                                        # 검색어가 포함된 조문이 1개라도 있으면 화면에 출력
                                        if found_texts:
                                            total_found_count += 1
                                            with st.expander(f"📌 [{t['label']}] {item_name}", expanded=True):
                                                for text in found_texts:
                                                    # 검색어 부분만 굵은 글씨로 강조
                                                    highlighted = text.replace(search_keyword, f"**{search_keyword}**")
                                                    st.write(f"- {highlighted}")
                                                
                                                full_link = f"https://www.law.go.kr{item_link}"
                                                st.markdown(f"[➡️ 이 {t['label']} 전체 원문 보기]({full_link})")
                                                
                except Exception as e:
                    st.error(f"{t['label']} 검색 중 오류가 발생했습니다: {e}")
                    
            if total_found_count == 0:
                st.info(f"'{search_keyword}'(이)가 본문에 포함된 법령이나 행정규칙을 찾지 못했습니다. 키워드를 조금 더 짧게 줄여보세요. (예: '단열재 두께' -> '단열재')")
            else:
                st.success("✅ 모든 분석이 완료되었습니다!")
