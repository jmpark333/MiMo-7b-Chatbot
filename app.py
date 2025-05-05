import streamlit as st
import requests
import json
import re
import uuid
import time

# API 엔드포인트 URL
API_URL = "http://127.0.0.1:1234/v1/chat/completions"

# Streamlit 앱 제목 설정
st.title("💬 MiMo-7B-RL 챗봇")

# 세션 상태 초기화 (대화 기록 저장용)
if "messages" not in st.session_state:
    st.session_state.messages = []
    # 시스템 프롬프트 강화 - 항상 최신 질문에 집중하도록 지시
    st.session_state.messages.append({
        "role": "system", 
        "content": """You must always answer in English. 
IMPORTANT: Always focus ONLY on the most recent user question. 
Do not refer to or answer previous questions unless explicitly asked to do so.
Each new question should be treated as a completely separate request.
Ignore any context from previous exchanges unless specifically referenced in the current question."""
    })
    # 각 메시지에 고유 ID 부여를 위한 카운터 초기화
    st.session_state.message_counter = 0
    # 마지막 질문 시간 기록
    st.session_state.last_question_time = time.time()

def process_latex(content):
    """LaTeX 수식을 처리하는 함수"""
    # 인라인 수식 처리 ($ ... $ 또는 \( ... \))
    content = re.sub(r'\\\((.*?)\\\)', r'$\1$', content, flags=re.DOTALL)
    
    # 디스플레이 수식 처리 (\[ ... \])
    content = re.sub(r'\\\[(.*?)\\\]', r'$$\1$$', content, flags=re.DOTALL)
    
    return content

def render_with_expanders(content):
    # Replace <think>...</think> blocks with collapsible markdown (details/summary)
    def replacer(match):
        inner = match.group(1)
        # HTML <details> 태그를 사용하여 접을 수 있는 섹션을 만듭니다.
        # 마크다운 내에서 HTML을 사용하므로 줄바꿈과 형식을 주의해야 합니다.
        return f'\n\n<details><summary>🤔 Think</summary>\n\n{inner}\n\n</details>\n\n'
    
    # 정규식을 사용하여 <think> 태그를 <details> 태그로 변환합니다.
    content = re.sub(r'<think>(.*?)</think>', replacer, content, flags=re.DOTALL)
    
    # LaTeX 수식을 처리합니다
    content = process_latex(content)
    
    return content

def render_message(message_content):
    """메시지를 렌더링하는 함수 - LaTeX 수식 포함"""
    # 수식 패턴 찾기
    math_pattern = r'\$(.*?)\$|\$\$(.*?)\$\$'
    
    # 메시지를 수식과 일반 텍스트로 분리
    parts = re.split(f'({math_pattern})', message_content, flags=re.DOTALL)
    
    for i, part in enumerate(parts):
        if part:
            # 수식 패턴에 맞는 경우
            if re.match(r'\$(.*?)\$', part):
                # 인라인 수식
                latex_expr = part[1:-1]  # $ 기호 제거
                st.latex(latex_expr)
            elif re.match(r'\$\$(.*?)\$\$', part):
                # 디스플레이 수식
                latex_expr = part[2:-2]  # $$ 기호 제거
                st.latex(latex_expr)
            else:
                # 일반 텍스트
                st.markdown(render_with_expanders(part), unsafe_allow_html=True)

# 이전 대화 내용 표시
for message in st.session_state.messages:
    # 시스템 메시지는 화면에 표시하지 않음
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            # 메시지 렌더링 함수 사용
            render_message(message["content"])

# 사용자 입력 받기
if prompt := st.chat_input("메시지를 입력하세요..."):
    # 현재 시간 기록
    current_time = time.time()
    
    # 사용자 메시지에 고유 ID 부여
    message_id = f"user_{st.session_state.message_counter}"
    st.session_state.message_counter += 1
    
    # 사용자 메시지를 대화 기록에 추가하고 화면에 표시
    user_message = {
        "role": "user", 
        "content": prompt, 
        "id": message_id,
        "timestamp": current_time
    }
    st.session_state.messages.append(user_message)
    
    with st.chat_message("user"):
        st.markdown(prompt) # 사용자 입력은 그대로 마크다운으로 표시

    # 이전 질문과 현재 질문 사이의 시간 간격 계산 (초 단위)
    time_since_last_question = current_time - st.session_state.last_question_time
    st.session_state.last_question_time = current_time
    
    # 질문 간격이 길면 컨텍스트 초기화 고려 (예: 5분 이상)
    if time_since_last_question > 300:  # 5분 = 300초
        # 시스템 메시지만 남기고 나머지 대화 기록 초기화
        system_message = next((msg for msg in st.session_state.messages if msg["role"] == "system"), None)
        if system_message:
            st.session_state.messages = [system_message, user_message]
            st.experimental_rerun()
            
    # API 요청 보내기
    try:
        # 요청 본문 생성 - 메시지 ID 제거한 버전 생성
        api_messages = []
        for msg in st.session_state.messages:
            # 필요한 필드만 포함
            api_msg = {"role": msg["role"], "content": msg["content"]}
            api_messages.append(api_msg)
            
        # 최신 질문에 집중하도록 하는 특별 메시지 추가
        api_messages.append({
            "role": "system",
            "content": f"IMPORTANT: The following is the CURRENT question you must answer now: '{prompt}'. Ignore all previous questions and focus ONLY on this one."
        })
            
        payload = {
            "model": "mimo-7b-rl",
            "messages": api_messages, # ID가 제거된 메시지 목록
            "temperature": 0.7,
            "max_tokens": -1,
            "stream": True
        }
        headers = {
            "Content-Type": "application/json"
        }

        # API 호출 (streaming)
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), stream=True)
        response.raise_for_status()
        response.encoding = 'utf-8'

        # 응답 메시지에 고유 ID 부여
        response_id = f"assistant_{st.session_state.message_counter}"
        st.session_state.message_counter += 1
        
        assistant_content = ""
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response_data = [] # For debugging
            try:
                for line in response.iter_lines(decode_unicode=True):
                    if line:
                        full_response_data.append(line)
                        if line.startswith("data: "):
                            line_content = line[len("data: "):].strip()
                        else:
                            line_content = line.strip()

                        if not line_content or line_content == "[DONE]":
                            if line_content == "[DONE]":
                                break
                            continue

                        try:
                            data = json.loads(line_content)
                            delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                assistant_content += delta
                                # 스트리밍 중에는 전체 메시지를 마크다운으로 표시
                                message_placeholder.markdown(assistant_content, unsafe_allow_html=True)
                        except json.JSONDecodeError:
                            st.warning(f"Skipping non-JSON line: {line_content[:100]}...")
                            continue
                        except Exception as e:
                            st.error(f"Error processing line: {e} - Line: {line_content[:100]}")
                            continue

            except Exception as stream_ex:
                 st.error(f"Error during streaming: {stream_ex}")
                 st.write("Raw response lines received before error:")
                 st.json(full_response_data)

            # 최종 메시지 저장 및 표시
            if assistant_content:
                 # 응답 메시지에 ID 포함하여 저장
                 assistant_message = {
                     "role": "assistant", 
                     "content": assistant_content,
                     "id": response_id,
                     "in_response_to": message_id,  # 어떤 사용자 메시지에 대한 응답인지 기록
                     "timestamp": time.time()
                 }
                 st.session_state.messages.append(assistant_message)
                 
                 # 최종 메시지를 컨테이너에 렌더링
                 message_container = st.container()
                 with message_container:
                     render_message(assistant_content)
                 
                 # 원래 placeholder는 비움
                 message_placeholder.empty()
            else:
                 st.warning("Assistant did not generate any content.")
                 st.write("Raw response lines received:")
                 st.json(full_response_data)

    except requests.exceptions.RequestException as e:
        st.error(f"API 요청 중 오류 발생: {e}")
    except Exception as e:
        st.error(f"처리 중 오류 발생: {e}")
        st.write("API 응답:", response.text if 'response' in locals() else "응답 없음")