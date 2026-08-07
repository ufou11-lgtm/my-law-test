# 파이썬 기본 환경 설정
FROM python:3.10-slim

WORKDIR /app

# 필요 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드 파일 복사
COPY . .

# 구글 클라우드 런을 위한 포트 설정 (8080)
EXPOSE 8080

# 스트림릿 앱 실행 명령어
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
