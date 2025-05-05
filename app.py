import streamlit as st
import requests
import json
import re

# API 엔드포인트 URL
API_URL = "http://127.0.0.1:1234/v1/chat/completions"

# Streamlit 앱 제목 설정
st.title("💬 Mimo-7b-rl Chatbot")

# 세션 상태 초기화 (대화 기록 저장용)
if "messages" not in st.session_state:
    st.session_state.messages = []
# Add a system prompt to instruct the chatbot to respond in English
    st.session_state.messages.append({"role": "system", "content": "You must always answer in English."})

def render_with_expanders(content):
    # Replace <think>...</think> blocks with collapsible markdown (details/summary)
    def replacer(match):
        inner = match.group(1)
        return f'\n\n<details><summary>🤔 Think</summary>\n\n{inner}\n\n</details>\n\n'
    content = re.sub(r'<think>(.*?)</think>', replacer, content, flags=re.DOTALL)
    return content

# 이전 대화 내용 표시
for message in st.session_state.messages:
    # 시스템 메시지는 화면에 표시하지 않음 (선택 사항)
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(render_with_expanders(message["content"]), unsafe_allow_html=True)

# 사용자 입력 받기
if prompt := st.chat_input("메시지를 입력하세요..."):
    # 사용자 메시지를 대화 기록에 추가하고 화면에 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # API 요청 보내기
    try:
        # 요청 본문 생성 (curl 명령어 참고, 이전 대화 포함)
        payload = {
            "model": "mimo-7b-rl",
            "messages": st.session_state.messages, # 전체 대화 기록 전달
            "temperature": 0.7,
            "max_tokens": -1, # 필요에 따라 조절
            "stream": True
        }
        headers = {
            "Content-Type": "application/json"
        }

        # API 호출 (streaming)
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), stream=True)
        response.raise_for_status() # 오류 발생 시 예외 발생
        response.encoding = 'utf-8' # 응답 인코딩을 UTF-8로 명시적으로 설정

        assistant_content = ""
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response_data = [] # For debugging
            try:
                for line in response.iter_lines(decode_unicode=True):
                    if line:
                        full_response_data.append(line) # Store raw line for debugging
                        # Check for SSE "data: " prefix
                        if line.startswith("data: "):
                            line_content = line[len("data: "):].strip()
                        else:
                            line_content = line.strip()

                        # Skip empty lines after stripping
                        if not line_content:
                            continue

                        # Handle potential end-of-stream markers (like "[DONE]")
                        if line_content == "[DONE]":
                            break

                        try:
                            data = json.loads(line_content)
                            # 응답 구조에 따라 조정 필요 (기존 로직 유지)
                            delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta: # Only append if delta is not empty
                                assistant_content += delta
                                # Update the placeholder progressively
                                message_placeholder.markdown(render_with_expanders(assistant_content), unsafe_allow_html=True)
                        except json.JSONDecodeError:
                            st.warning(f"Skipping non-JSON line: {line_content[:100]}...") # Log parsing errors clearly
                            continue # Skip lines that cannot be parsed as JSON
                        except Exception as e: # Catch other potential errors during processing
                            st.error(f"Error processing line: {e} - Line: {line_content[:100]}")
                            continue

            except Exception as stream_ex:
                 st.error(f"Error during streaming: {stream_ex}")
                 st.write("Raw response lines received before error:") # Debugging output
                 st.json(full_response_data) # Show raw data if streaming fails


            # Ensure the final message is stored even if the loop ends or breaks
            if assistant_content:
                 assistant_message = {"role": "assistant", "content": assistant_content}
                 st.session_state.messages.append(assistant_message)
                 # Final update to placeholder just in case last chunk wasn't rendered
                 message_placeholder.markdown(render_with_expanders(assistant_content), unsafe_allow_html=True)
            else:
                 st.warning("Assistant did not generate any content.")
                 st.write("Raw response lines received:") # Debugging output
                 st.json(full_response_data) # Show raw data if nothing was generated

    except requests.exceptions.RequestException as e:
        st.error(f"API 요청 중 오류 발생: {e}")
    except Exception as e:
        st.error(f"처리 중 오류 발생: {e}")
        st.write("API 응답:", response.text if 'response' in locals() else "응답 없음") # 디버깅용