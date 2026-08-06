# 1. 파이썬이 설치된 가상의 컴퓨터(컨테이너)를 준비합니다.
FROM python:3.9-slim

# 2. 가상 컴퓨터 안에서 작업할 기본 폴더를 /app 으로 정합니다.
WORKDIR /app

# 3. 내 컴퓨터에 있는 requirements.txt 파일을 가상 컴퓨터로 복사합니다.
COPY requirements.txt .

# 4. 복사한 파일을 보고 필요한 부품(라이브러리)들을 가상 컴퓨터에 설치합니다.
RUN pip install --no-cache-dir -r requirements.txt

# 5. 이제 app.py를 포함한 나머지 모든 파일을 가상 컴퓨터로 복사합니다.
COPY . .

# 6. 구글 클라우드가 사용할 포트(포트 번호 8080)를 열어둡니다.
EXPOSE 8080

# 7. 마지막으로 스트림릿을 실행하여 웹사이트를 켭니다.
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]