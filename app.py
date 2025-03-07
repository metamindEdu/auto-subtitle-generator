import os
import tempfile
import torch
import streamlit as st
import whisper
import pysrt
import numpy as np
import warnings
import collections
import contextlib
import wave
import subprocess
from tqdm import tqdm
from datetime import timedelta
import time
import re
from dotenv import load_dotenv
from openai import OpenAI
import anthropic

# .env 파일 로드
load_dotenv()

warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")
warnings.filterwarnings("ignore", category=FutureWarning)

def check_gpu_status():
    """GPU 감지 및 사용 상태를 확인하는 함수"""
    gpu_info = {
        "is_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "current_device": None,
        "device_name": None,
        "memory_allocated": None,
        "memory_reserved": None,
        "memory_total": None
    }
    
    if gpu_info["is_available"]:
        current_device = torch.cuda.current_device()
        gpu_info["current_device"] = current_device
        gpu_info["device_name"] = torch.cuda.get_device_name(current_device)
        
        # 단위 변환 함수 (바이트 -> GB)
        def bytes_to_gb(bytes_value):
            return round(bytes_value / (1024**3), 2)
        
        try:
            gpu_info["memory_allocated"] = bytes_to_gb(torch.cuda.memory_allocated(current_device))
            gpu_info["memory_reserved"] = bytes_to_gb(torch.cuda.memory_reserved(current_device))
            
            # 전체 VRAM 용량 확인 (Windows 전용)
            if os.name == 'nt':
                try:
                    # nvidia-smi 명령어 실행
                    import subprocess
                    result = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'], 
                                               universal_newlines=True)
                    memory_total = int(result.strip())
                    gpu_info["memory_total"] = memory_total / 1024  # MB -> GB
                except:
                    gpu_info["memory_total"] = "확인 불가"
            else:
                gpu_info["memory_total"] = "확인 불가"
        except:
            # 메모리 정보를 가져올 수 없는 경우
            gpu_info["memory_allocated"] = "확인 불가"
            gpu_info["memory_reserved"] = "확인 불가"
            gpu_info["memory_total"] = "확인 불가"
    
    return gpu_info

def display_gpu_info():
    """GPU 정보를 Streamlit UI에 표시하는 함수"""
    gpu_info = check_gpu_status()
    
    # GPU 사용 가능 여부에 따라 다른 색상 및 메시지 표시
    if gpu_info["is_available"]:
        st.success("🎮 GPU 감지됨!")
        
        # GPU 정보 표시
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("감지된 GPU 수", gpu_info["device_count"])
            st.write(f"**모델**: {gpu_info['device_name']}")
        
        with col2:
            if isinstance(gpu_info["memory_allocated"], (int, float)):
                st.metric("사용 중인 VRAM", f"{gpu_info['memory_allocated']} GB")
            else:
                st.write("**사용 중인 VRAM**: 확인 불가")
                
            if isinstance(gpu_info["memory_total"], (int, float)):
                st.metric("전체 VRAM", f"{round(gpu_info['memory_total'], 1)} GB")
            else:
                st.write("**전체 VRAM**: 확인 불가")
        
        # Whisper 모델의 GPU 사용 설정
        st.info(f"🔍 Whisper 모델 확인: GPU 사용이 가능합니다! {gpu_info['device_name']}에서 사용률이 낮은 경우 GPU 부하가 낮거나 CPU로 일부 작업이 처리될 수 있습니다.")
        
        # 환경 변수 확인 - expander 사용하지 않고 직접 표시
        st.subheader("🛠️ GPU 최적화 설정 확인")
        cuda_env_vars = {
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES", "설정되지 않음"),
            "PYTORCH_CUDA_ALLOC_CONF": os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "설정되지 않음"),
            "TF_FORCE_GPU_ALLOW_GROWTH": os.environ.get("TF_FORCE_GPU_ALLOW_GROWTH", "설정되지 않음")
        }
        
        for var_name, var_value in cuda_env_vars.items():
            st.write(f"**{var_name}**: {var_value}")
        
        if all(value == "설정되지 않음" for value in cuda_env_vars.values()):
            st.warning("GPU 관련 환경 변수가 설정되지 않았습니다. 필요한 경우 최적화를 위해 환경 변수를 설정하세요.")
        
        # Torch 버전 정보
        st.write(f"**PyTorch 버전**: {torch.__version__}")
        st.write(f"**CUDA 버전**: {torch.version.cuda or '사용 불가'}")
    else:
        st.warning("⚠️ GPU가 감지되지 않았습니다. CPU 모드로 실행됩니다.")
        st.write("Whisper 모델은 CPU에서도 작동하지만, 처리 속도가 느립니다.")
        
        # 가능한 원인 및 해결책 - expander 없이 직접 표시
        st.subheader("가능한 원인 및 해결책")
        st.write("""
        - **CUDA가 설치되지 않음**: PyTorch CUDA 버전을 설치하세요: `pip install torch --index-url https://download.pytorch.org/whl/cu121`
        - **드라이버 문제**: 최신 NVIDIA 드라이버가 설치되어 있는지 확인하세요.
        - **CUDA 버전 불일치**: PyTorch와 호환되는 CUDA 버전을 설치하세요.
        - **환경 변수 문제**: 'CUDA_VISIBLE_DEVICES' 환경 변수가 올바르게 설정되어 있는지 확인하세요.
        """)

# 세션 상태 초기화
if 'vad_module_loaded' not in st.session_state:
    st.session_state.vad_module_loaded = False

# VAD 모듈 로드 시도
try:
    import webrtcvad
    st.session_state.vad_module_loaded = True
except ImportError:
    st.warning("webrtcvad 모듈이 설치되지 않았습니다. 'pip install webrtcvad'로 설치하세요. VAD 없이 계속 진행합니다.")

class Frame(object):
    """VAD를 위한 프레임 클래스"""
    def __init__(self, bytes, timestamp, duration):
        self.bytes = bytes
        self.timestamp = timestamp
        self.duration = duration

def frame_generator(frame_duration_ms, audio, sample_rate):
    """오디오를 프레임으로 분할"""
    n = int(sample_rate * (frame_duration_ms / 1000.0) * 2)
    offset = 0
    timestamp = 0.0
    duration = (float(n) / sample_rate) / 2.0
    while offset + n < len(audio):
        yield Frame(audio[offset:offset + n], timestamp, duration)
        timestamp += duration
        offset += n

def vad_collector(sample_rate, frame_duration_ms, padding_duration_ms, vad, frames):
    """VAD를 사용하여 음성 구간 감지"""
    num_padding_frames = int(padding_duration_ms / frame_duration_ms)
    ring_buffer = collections.deque(maxlen=num_padding_frames)
    triggered = False
    voiced_frames = []
    
    for frame in frames:
        is_speech = vad.is_speech(frame.bytes, sample_rate)
        
        if not triggered:
            ring_buffer.append((frame, is_speech))
            num_voiced = len([f for f, speech in ring_buffer if speech])
            
            if num_voiced > 0.9 * ring_buffer.maxlen:
                triggered = True
                for f, s in ring_buffer:
                    voiced_frames.append(f)
                ring_buffer.clear()
        else:
            voiced_frames.append(frame)
            ring_buffer.append((frame, is_speech))
            num_unvoiced = len([f for f, speech in ring_buffer if not speech])
            
            if num_unvoiced > 0.9 * ring_buffer.maxlen:
                triggered = False
                yield (voiced_frames[0].timestamp,
                      voiced_frames[-1].timestamp + voiced_frames[-1].duration,
                      b''.join([f.bytes for f in voiced_frames]))
                ring_buffer.clear()
                voiced_frames = []
    
    if voiced_frames:
        yield (voiced_frames[0].timestamp,
               voiced_frames[-1].timestamp + voiced_frames[-1].duration,
               b''.join([f.bytes for f in voiced_frames]))

def process_with_vad(audio_path, aggressiveness=1):
    """VAD를 사용하여 음성 구간 처리"""
    if not st.session_state.vad_module_loaded:
        # VAD를 사용할 수 없는 경우 전체 오디오를 하나의 세그먼트로 처리
        import soundfile as sf
        info = sf.info(audio_path)
        return [(0, info.duration)]
    
    with contextlib.closing(wave.open(audio_path, 'rb')) as wf:
        pcm_data = wf.readframes(wf.getnframes())
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
    
    vad = webrtcvad.Vad(aggressiveness)
    frames = frame_generator(30, pcm_data, sample_rate)
    frames = list(frames)
    segments = vad_collector(sample_rate, 30, 2000, vad, frames)
    
    voice_segments = []
    for start, end, _ in segments:
        voice_segments.append((start, end))
    
    return voice_segments

class PromptManager:
    def __init__(self, prompts_dir="prompts"):
        self.prompts_dir = prompts_dir
        self.system_prompt = self._load_prompt("system_prompt.md")
        self.user_prompt_template = self._load_prompt("user_prompt.md")
    
    def _load_prompt(self, filename):
        """마크다운 파일에서 프롬프트 로드"""
        try:
            prompt_path = os.path.join(self.prompts_dir, filename)
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            st.error(f"프롬프트 파일 로드 중 오류 발생 ({filename}): {str(e)}")
            return ""
    
    def get_user_prompt(self, context, current_sub, previous_subs, next_subs):
        """사용자 프롬프트 생성"""
        return self.user_prompt_template.format(
            context=context or '없음',
            previous_subs='\n'.join(previous_subs) if previous_subs else '없음',
            current_sub=current_sub,
            next_subs='\n'.join(next_subs) if next_subs else '없음'
        )

class SubtitleGenerator:
    def __init__(self, model_size="small", llm_provider=None):
        with st.spinner("Whisper 모델 로딩 중..."):
            self.model = whisper.load_model(model_size)
        st.success("모델 로딩 완료!")

        self.llm_provider = llm_provider
        self.prompt_manager = PromptManager()
        
        self.llm_client = None
        if llm_provider == "openai":
            openai_api_key = os.getenv("OPENAI_API_KEY") or st.session_state.get('openai_api_key')
            if openai_api_key:
                self.llm_client = OpenAI(api_key=openai_api_key)
            else:
                st.warning("OpenAI API 키가 필요합니다. 설정에서 입력해주세요.")
        elif llm_provider == "anthropic":
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or st.session_state.get('anthropic_api_key')
            if anthropic_api_key:
                self.llm_client = anthropic.Anthropic(api_key=anthropic_api_key)
            else:
                st.warning("Anthropic API 키가 필요합니다. 설정에서 입력해주세요.")
    
    def convert_to_wav(self, input_file):
        """업로드된 파일을 WAV 형식으로 변환"""
        try:
            # 임시 파일 생성
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_wav:
                temp_wav_path = temp_wav.name
            
            # 원본 파일을 임시 파일로 저장
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(input_file.name)[1]) as temp_input:
                temp_input.write(input_file.getbuffer())
                temp_input_path = temp_input.name
            
            # FFmpeg를 사용한 변환
            try:
                import ffmpeg
                
                # FFmpeg를 사용하여 변환
                (
                    ffmpeg
                    .input(temp_input_path)
                    .output(temp_wav_path, acodec='pcm_s16le', ar=16000, ac=1)
                    .run(quiet=True, overwrite_output=True)
                )
                
                # 파일 길이 확인
                probe = ffmpeg.probe(temp_wav_path)
                audio_info = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
                total_seconds = float(audio_info.get('duration', 0))
                
                return temp_wav_path, total_seconds, temp_input_path
                
            except ImportError:
                st.error("ffmpeg-python 패키지가 설치되지 않았습니다. 'pip install ffmpeg-python'으로 설치하세요.")
                raise
            except ffmpeg.Error as e:
                st.error(f"FFmpeg 변환 오류: {e.stderr.decode() if e.stderr else str(e)}")
                raise
                
        except Exception as e:
            st.error(f"오디오 변환 중 오류 발생: {str(e)}")
            import traceback
            st.error(traceback.format_exc())
            
            # 임시 파일 정리
            if 'temp_input_path' in locals() and os.path.exists(temp_input_path):
                os.unlink(temp_input_path)
            if 'temp_wav_path' in locals() and os.path.exists(temp_wav_path):
                os.unlink(temp_wav_path)
                
            return None, None, None

    def merge_short_subtitles(self, subtitles, min_chars):
        """짧은 자막들을 병합"""
        if not subtitles:
            return subtitles
        
        merged = []
        current = subtitles[0]
        
        for next_sub in subtitles[1:]:
            # 현재 자막이 최소 글자 수보다 적고, 다음 자막과의 시간 간격이 2초 이내인 경우
            if (len(current.text) < min_chars and 
                (next_sub.start.hours * 3600 + next_sub.start.minutes * 60 + next_sub.start.seconds) - 
                (current.end.hours * 3600 + current.end.minutes * 60 + current.end.seconds) <= 2):
                
                # 병합된 텍스트가 최대 글자 수를 초과하지 않는 경우에만 병합
                if len(current.text + " " + next_sub.text) <= 100:  # 기본 최대 글자 수 제한
                    current.text += " " + next_sub.text
                    current.end = next_sub.end
                else:
                    merged.append(current)
                    current = next_sub
            else:
                merged.append(current)
                current = next_sub
        
        merged.append(current)
        
        # 인덱스 재정렬
        for i, sub in enumerate(merged, 1):
            sub.index = i
        
        return merged

    def correct_subtitle_with_llm(self, subtitle_text, context=None, previous_subs=None, next_subs=None):
        """LLM을 사용하여 자막 텍스트를 교정"""
        if not self.llm_client:
            return subtitle_text
        
        try:
            # 원본 자막 로그 추가
            log_entry = f"원본 자막: {subtitle_text}"
            if 'correction_logs' not in st.session_state:
                st.session_state.correction_logs = []
            st.session_state.correction_logs.append(log_entry)
            
            if self.llm_provider == "openai":
                response = self.llm_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": self.prompt_manager.system_prompt},
                        {"role": "user", "content": self.prompt_manager.get_user_prompt(
                            context, subtitle_text, previous_subs, next_subs
                        )}
                    ],
                    temperature=0.3
                )
                corrected_text = response.choices[0].message.content.strip()
                
            elif self.llm_provider == "anthropic":
                response = self.llm_client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=8000,
                    temperature=0.3,
                    system=self.prompt_manager.system_prompt,
                    messages=[{
                        "role": "user", 
                        "content": self.prompt_manager.get_user_prompt(
                            context, subtitle_text, previous_subs, next_subs
                        )
                    }]
                )
                corrected_text = response.content[0].text.strip()
            
            # 교정된 자막 로그 추가
            log_entry = f"교정된 자막: {corrected_text}"
            st.session_state.correction_logs.append(log_entry)
            
            # 자동 스크롤을 위해 세션 상태 업데이트
            st.session_state.log_updated = True
            
            return corrected_text
                
        except Exception as e:
            error_msg = f"자막 교정 중 오류 발생: {str(e)}"
            st.session_state.correction_logs.append(error_msg)
            return subtitle_text
        
    def _update_correction_log_display(self, log_placeholder):
        """교정 로그 디스플레이 업데이트"""
        if 'correction_logs' not in st.session_state or not st.session_state.correction_logs:
            return
        
        # HTML 형식으로 로그 구성
        log_html = "<div class='log-container' id='log-container'>"
        reversed_logs = list(reversed(st.session_state.correction_logs))
        
        for i, log in enumerate(reversed_logs):
            if "원본 자막:" in log:
                log_html += f"<div class='original-subtitle'>{log}</div>"
            elif "교정된 자막:" in log:
                if i < len(st.session_state.correction_logs) - 1:
                    log_html += "<div class='log-divider'></div>"
                log_html += f"<div class='corrected-subtitle'>{log}</div>"
            elif "오류" in log:
                log_html += f"<div class='error-message'>{log}</div>"
        
        log_html += "</div>"
        
        # 로그 표시
        log_placeholder.markdown(log_html, unsafe_allow_html=True)

    def generate_subtitles(self, audio_file, progress_bar, status_text, language=None, max_chars=None, min_chars=None, max_duration=None, context=None, vad_enabled=True, vad_aggressiveness=1):
        """자막 생성 함수"""
        temp_files = []

        # 로그 컨테이너 초기화
        st.session_state.correction_logs = []
        process_container = st.container()
        status_container = process_container.container()
        log_container = process_container.container()
        # 교정 로그 스타일 정의
        log_container.markdown("""
        <style>
        .log-container {
            height: 250px;
            overflow-y: auto;
            background-color: #f0f2f6;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 10px;
            font-family: monospace;
            border: 1px solid #ddd;
        }
        .original-subtitle {
            color: #555;
            margin-bottom: 4px;
        }
        .corrected-subtitle {
            color: #0066cc;
            margin-bottom: 12px;
            font-weight: bold;
        }
        .error-message {
            color: #cc0000;
            font-weight: bold;
        }
        .log-divider {
            border-bottom: 1px dashed #ccc;
            margin: 8px 0;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # 로그 표시 영역
        log_heading = log_container.empty()
        log_placeholder = log_container.empty()
        
        # 로그 제목 설정
        if self.llm_client:
            log_heading.subheader("실시간 자막 교정 로그")
        
        try:
            # WAV 파일 생성
            wav_path, total_seconds, temp_input_path = self.convert_to_wav(audio_file)
            if not wav_path:
                return None
            
            temp_files.extend([wav_path, temp_input_path])
            status_text.text("WAV 파일 생성 완료")
            progress_bar.progress(10)
            
            # VAD를 사용하여 음성 구간 감지
            if vad_enabled:
                status_text.text("음성 구간 감지 중...")
                voice_segments = process_with_vad(wav_path, vad_aggressiveness)
                status_text.text(f"감지된 음성 구간: {len(voice_segments)}개")
            else:
                # VAD를 사용하지 않는 경우 전체 오디오를 하나의 세그먼트로 처리
                import soundfile as sf
                info = sf.info(wav_path)
                voice_segments = [(0, info.duration)]
                status_text.text("VAD 비활성화: 전체 오디오를 한 번에 처리합니다")
                
            progress_bar.progress(20)
            
            # 전체 자막 정보 저장용
            all_segments = []
            
            # 오디오 파일 로드
            import soundfile as sf
            audio, sample_rate = sf.read(wav_path)
            audio = audio.astype(np.float32)
            
            # 음성 구간 처리
            status_text.text("음성 인식 시작...")
            total_segments = len(voice_segments)
            
            for i, (start, end) in enumerate(voice_segments):
                status_text.text(f"음성 구간 {i+1}/{total_segments} 처리 중...")
                
                # 진행률 업데이트
                segment_progress = 20 + (i / total_segments * 40)
                progress_bar.progress(int(segment_progress))
                
                # 현재 구간의 오디오 추출
                start_sample = int(start * sample_rate)
                end_sample = min(int(end * sample_rate), len(audio))
                segment_audio = audio[start_sample:end_sample]
                
                # Whisper로 음성 인식
                transcribe_options = {}
                if language:
                    transcribe_options["language"] = language
                    
                result = self.model.transcribe(segment_audio, **transcribe_options)
                
                # 세그먼트 시간 조정
                for segment in result["segments"]:
                    segment["start"] = start + segment["start"]
                    segment["end"] = start + segment["end"]
                    all_segments.append(segment)
            
            status_text.text("음성 인식 완료!")
            progress_bar.progress(60)
            
            # 자막 파일 생성
            status_text.text("자막 파일 생성 중...")
            subs = pysrt.SubRipFile()
            subtitle_index = 1
            
            # 전체 세그먼트 수
            total_segments = len(all_segments)
            
            # 자막 생성
            for i, segment in enumerate(all_segments):
                # 이전/다음 자막 컨텍스트 수집
                previous_subs = [seg["text"].strip() for seg in all_segments[max(0, i-2):i]]
                next_subs = [seg["text"].strip() for seg in all_segments[i+1:i+3]]
                
                # 진행률 업데이트
                if self.llm_client:
                    segment_progress = 20 + ((i / total_segments) * 70)
                else:
                    segment_progress = 20 + ((i / total_segments) * 40)

                progress_bar.progress(int(segment_progress))
                
                # LLM으로 자막 교정
                if self.llm_client:
                    status_text.text(f"자막 교정 중... ({i+1}/{total_segments})")
                    
                    text = self.correct_subtitle_with_llm(
                        segment["text"].strip(), context, previous_subs, next_subs
                    )
                    
                    # 로그 업데이트 및 화면 갱신
                    self._update_correction_log_display(log_placeholder)
                else:
                    text = segment["text"].strip()
                
                if not text:  # 빈 텍스트는 건너뛰기
                    continue
                
                # 시간 정보 추출
                start_time = segment["start"]
                end_time = segment["end"]
                duration = end_time - start_time
                
                # 최대 시간 길이 체크
                if max_duration and duration > max_duration:
                    # 디버깅 정보 추가
                    status_text.text(f"긴 자막 분할: {duration:.2f}초 > {max_duration:.2f}초")
                    
                    # 시간 간격으로 분할
                    num_splits = int(np.ceil(duration / max_duration))
                    sub_duration = duration / num_splits
                    
                    # 텍스트를 단어 단위로 분할하여 시간에 맞게 재분배
                    words = text.split()
                    words_per_split = len(words) // num_splits
                    splits = []
                    
                    for j in range(num_splits):
                        sub_start = start_time + (j * sub_duration)
                        sub_end = sub_start + sub_duration if j < num_splits - 1 else end_time
                        
                        if j == num_splits - 1:
                            # 마지막 분할은 남은 모든 단어 사용
                            sub_words = words[j * words_per_split:]
                        else:
                            # 단어 단위로 분할
                            start_idx = j * words_per_split
                            end_idx = (j + 1) * words_per_split
                            sub_words = words[start_idx:end_idx]
                        
                        sub_text = ' '.join(sub_words).strip()
                        if sub_text:  # 빈 텍스트가 아닌 경우만 추가
                            splits.append((sub_start, sub_end, sub_text))
                else:
                    splits = [(start_time, end_time, text)]
                
                # 최대 글자 수 제한 처리
                final_splits = []
                for sub_start, sub_end, sub_text in splits:
                    if max_chars and len(sub_text) > max_chars:
                        # 텍스트를 최대 글자 수로 분할
                        words = sub_text.split()
                        current_text = ""
                        sub_splits = []
                        
                        for word in words:
                            if len(current_text) + len(word) + 1 <= max_chars:
                                current_text += (" " + word if current_text else word)
                            else:
                                if current_text:
                                    sub_splits.append(current_text)
                                current_text = word
                        
                        if current_text:  # 마지막 부분 추가
                            sub_splits.append(current_text)
                        
                        # 시간을 텍스트 길이에 비례하여 분배
                        sub_duration = sub_end - sub_start
                        total_chars = sum(len(s) for s in sub_splits)
                        current_time = sub_start
                        
                        for sub_text in sub_splits:
                            ratio = len(sub_text) / total_chars
                            split_duration = sub_duration * ratio
                            split_end = current_time + split_duration
                            
                            final_splits.append((current_time, split_end, sub_text))
                            current_time = split_end
                    else:
                        final_splits.append((sub_start, sub_end, sub_text))
                
                # 자막 생성
                for start, end, text in final_splits:
                    if text.strip():
                        hours = int(start) // 3600
                        minutes = (int(start) % 3600) // 60
                        seconds = int(start) % 60
                        milliseconds = int((start % 1) * 1000)
                        start_time = pysrt.SubRipTime(hours=hours, minutes=minutes, 
                                                    seconds=seconds, milliseconds=milliseconds)
                        
                        hours = int(end) // 3600
                        minutes = (int(end) % 3600) // 60
                        seconds = int(end) % 60
                        milliseconds = int((end % 1) * 1000)
                        end_time = pysrt.SubRipTime(hours=hours, minutes=minutes, 
                                                seconds=seconds, milliseconds=milliseconds)
                        
                        sub = pysrt.SubRipItem(
                            index=subtitle_index,
                            start=start_time,
                            end=end_time,
                            text=text
                        )
                        subs.append(sub)
                        subtitle_index += 1
            
            # 최소 글자 수 제한이 설정된 경우 짧은 자막 병합
            if min_chars:
                status_text.text("짧은 자막 병합 중...")
                merged_subs = self.merge_short_subtitles(subs, min_chars)
                subs = pysrt.SubRipFile()
                for sub in merged_subs:
                    subs.append(sub)
            
            # 임시 SRT 파일 생성
            with tempfile.NamedTemporaryFile(delete=False, suffix='.srt') as temp_srt:
                temp_srt_path = temp_srt.name
                temp_files.append(temp_srt_path)
            
            subs.save(temp_srt_path, encoding='utf-8')
            status_text.text("자막 파일 생성 완료!")
            progress_bar.progress(100)
            
            # SRT 파일 내용 읽기
            with open(temp_srt_path, 'r', encoding='utf-8') as f:
                srt_content = f.read()
            
            return srt_content
            
        except Exception as e:
            st.error(f"자막 생성 중 오류 발생: {str(e)}")
            import traceback
            st.error(traceback.format_exc())
            return None
            
        finally:
            # 임시 파일 정리
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

    def convert_srt_to_vtt(self, srt_content):
        """SRT 형식의 자막을 VTT 형식으로 변환합니다."""
        # VTT 헤더 추가
        vtt_content = "WEBVTT\n\n"
        
        # SRT 블록 단위로 분할
        srt_blocks = srt_content.strip().split('\n\n')
        
        for block in srt_blocks:
            lines = block.split('\n')
            
            # 각 블록은 최소 3줄 이상이어야 함 (인덱스, 시간, 텍스트)
            if len(lines) >= 3:
                # 인덱스 라인은 건너뛰기
                
                # 시간 포맷 변환 (00:00:00,000 --> 00:00:00.000)
                time_line = lines[1].replace(',', '.')
                
                # 텍스트 라인 유지
                text_lines = lines[2:]
                
                # VTT 블록 생성
                vtt_block = time_line + '\n' + '\n'.join(text_lines)
                vtt_content += vtt_block + '\n\n'
        
        return vtt_content

def save_to_subtitle_history(filename, srt_content, vtt_content=None, correction_logs=None):
    """자막과 교정 로그를 히스토리에 저장하고 생성된 ID를 반환하는 함수"""
    if not filename or not srt_content:
        return None
    
    # 고유 식별자 생성 (파일명 + 타임스탬프)
    current_time = time.time()
    unique_id = f"{filename}_{current_time}"
    
    # 중복 확인
    exists = False
    existing_id = None
    for item in st.session_state.subtitle_history:
        if item['filename'] == filename and item['content'] == srt_content:
            exists = True
            existing_id = item.get('id')
            break
    
    # 중복이 아닌 경우에만 저장
    if not exists:
        # 자막 히스토리에 저장
        st.session_state.subtitle_history.append({
            'id': unique_id,
            'filename': filename,
            'content': srt_content,
            'vtt_content': vtt_content,
            'timestamp': current_time
        })
        
        # 교정 로그가 있으면 로그 히스토리에 저장
        if correction_logs:
            st.session_state.correction_logs_history[unique_id] = correction_logs.copy()
        
        # 목록이 너무 길어지는 것을 방지 (최대 10개 저장)
        if len(st.session_state.subtitle_history) > 10:
            # 가장 오래된 항목 제거
            oldest_item = st.session_state.subtitle_history.pop(0)
            # 관련 로그도 제거
            if oldest_item.get('id') in st.session_state.correction_logs_history:
                del st.session_state.correction_logs_history[oldest_item['id']]
        
        return unique_id
    else:
        # 이미 존재하는 경우 기존 ID 반환
        return existing_id

def main():
    st.set_page_config(
        page_title="자동 자막 생성기",
        page_icon="🎬",
        layout="wide"
    )

    # 세션 상태 초기화
    if 'vad_module_loaded' not in st.session_state:
        st.session_state.vad_module_loaded = False
    if 'openai_api_key' not in st.session_state:
        st.session_state.openai_api_key = ""
    if 'anthropic_api_key' not in st.session_state:
        st.session_state.anthropic_api_key = ""
    if 'last_srt_content' not in st.session_state:
        st.session_state.last_srt_content = None
    if 'last_filename' not in st.session_state:
        st.session_state.last_filename = None
    if 'show_last_preview' not in st.session_state:
        st.session_state.show_last_preview = False
    if 'correction_logs' not in st.session_state:
        st.session_state.correction_logs = []
    if 'subtitle_history' not in st.session_state:
        st.session_state.subtitle_history = []
    if 'correction_logs_history' not in st.session_state:
        st.session_state.correction_logs_history = {}

    # 교정 로그 표시 영역 생성
    if 'show_logs' not in st.session_state:
        st.session_state.show_logs = False
    
    # VAD 모듈 로드 시도
    try:
        import webrtcvad
        st.session_state.vad_module_loaded = True
    except ImportError:
        st.warning("webrtcvad 모듈이 설치되지 않았습니다. 'pip install webrtcvad'로 설치하세요. VAD 없이 계속 진행합니다.")
    
    # 사이드바 - 설정
    with st.sidebar:
        st.title("⚙️ 설정")

        with st.expander("GPU 정보", expanded=False):
            display_gpu_info()

        if torch.cuda.is_available():
            with st.expander("GPU 최적화 옵션", expanded=False):
                st.info("최신 GPU는 Whisper 모델에는 높은 사용률이 필요하지 않을 수 있습니다.")
                use_half_precision = st.checkbox("Half Precision 사용 (FP16, 메모리 절약)", value=True)
                device_id = st.selectbox(
                    "GPU 장치 선택", 
                    options=list(range(torch.cuda.device_count())),
                    format_func=lambda x: f"GPU {x}: {torch.cuda.get_device_name(x)}",
                    index=0
                )
                
                if use_half_precision:
                    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:128"
        
        # API 키 설정
        with st.expander("API 키 설정", expanded=False):
            openai_key = st.text_input(
                "OpenAI API 키", 
                type="password", 
                value=st.session_state.openai_api_key,
                key="openai_api_key_input"
            )
            anthropic_key = st.text_input(
                "Anthropic API 키", 
                type="password", 
                value=st.session_state.anthropic_api_key,
                key="anthropic_api_key_input"
            )
            
            if openai_key:
                os.environ["OPENAI_API_KEY"] = openai_key
                st.session_state.openai_api_key = openai_key
            
            if anthropic_key:
                os.environ["ANTHROPIC_API_KEY"] = anthropic_key
                st.session_state.anthropic_api_key = anthropic_key
        
        # 모델 설정
        whisper_model = st.selectbox(
            "Whisper 모델 크기",
            options=["tiny", "base", "small", "medium", "large"],
            index=2
        )
        
        llm_provider = st.radio(
            "LLM 교정 제공자",
            options=["사용안함", "OpenAI", "Anthropic"],
            index=0
        )
        
        if llm_provider == "OpenAI":
            llm_provider = "openai"
        elif llm_provider == "Anthropic":
            llm_provider = "anthropic"
        else:
            llm_provider = None
        
        # VAD 설정
        vad_enabled = st.checkbox("VAD(Voice Activity Detection) 사용", value=True, 
                               help="음성이 있는 부분만 감지하여 처리합니다. 비활성화하면 전체 오디오를 한 번에 처리합니다.")
        
        if vad_enabled and st.session_state.vad_module_loaded:
            vad_aggressiveness = st.slider("VAD 감도", min_value=0, max_value=3, value=1, 
                                        help="높을수록 더 엄격하게 음성을 감지합니다. 0: 매우 관대, 3: 매우 엄격")
        else:
            vad_aggressiveness = 1
        
        # 자막 설정
        language = st.selectbox(
            "자막 언어",
            options=["자동 감지", "한국어", "영어", "일본어", "중국어"],
            index=0
        )
        
        lang_code = None
        if language == "한국어":
            lang_code = "ko"
        elif language == "영어":
            lang_code = "en"
        elif language == "일본어":
            lang_code = "ja"
        elif language == "중국어":
            lang_code = "zh"
        
        max_chars = st.number_input("한 자막당 최대 글자 수", min_value=0, value=40)
        if max_chars <= 0:
            max_chars = None
            
        min_chars = st.number_input("한 자막당 최소 글자 수", min_value=0, value=6)
        if min_chars <= 0:
            min_chars = None
            
        max_duration = st.number_input("한 자막당 최대 시간(초)", min_value=0.0, value=5.0)
        if max_duration <= 0:
            max_duration = None
        
        context = st.text_area("영상 컨텍스트 (영상의 주제, 목적, 대상 청중 등)", height=100)
        if not context:
            context = None
    
    # 메인 컨텐츠
    st.title("🎬 자동 자막 생성기")
    st.write("음성 또는 영상 파일을 업로드하여 자동으로 자막을 생성하세요.")
    
    # 고급 옵션
    with st.expander("옵션 설명", expanded=False):
        st.info("VAD(Voice Activity Detection)는 오디오에서 음성이 있는 부분만 감지하여 처리합니다. 중간 중간 오디오 공백이 있는 영상 및 음성 파일에서 효과적입니다.")
        st.warning("webrtcvad 모듈이 설치되지 않은 경우 VAD 기능이 비활성화됩니다.")
    
    # 자막 히스토리 표시
    if 'subtitle_history' in st.session_state and len(st.session_state.subtitle_history) > 0:
        with st.expander("이전 자막 히스토리", expanded=False):
            for i, item in enumerate(reversed(st.session_state.subtitle_history)):
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                with col1:
                    st.write(f"{item['filename']} ({time.strftime('%Y-%m-%d %H:%M', time.localtime(item['timestamp']))})")
                
                with col2:
                    st.download_button(
                        label="SRT",
                        data=item['content'],
                        file_name=f"{item['filename'].split('.')[0]}.srt",
                        mime="text/plain",
                        key=f"srt_download_{i}",
                        use_container_width=True
                    )
                
                with col3:
                    if item.get('vtt_content'):
                        st.download_button(
                            label="VTT",
                            data=item['vtt_content'],
                            file_name=f"{item['filename'].split('.')[0]}.vtt",
                            mime="text/plain",
                            key=f"vtt_download_{i}",
                            use_container_width=True
                        )
                    else:
                        st.write("VTT 없음")
                
                with col4:
                    if st.button("로드", key=f"load_history_{i}", use_container_width=True):
                        # 현재 표시 중인 자막이 있으면 히스토리에 저장 (히스토리 로드 전에)
                        if st.session_state.last_srt_content is not None and st.session_state.last_filename is not None:
                            save_to_subtitle_history(
                                st.session_state.last_filename,
                                st.session_state.last_srt_content,
                                st.session_state.get('last_vtt_content'),
                                st.session_state.get('correction_logs', [])
                            )
                        
                        # 히스토리에서 선택한 자막 로드
                        st.session_state.last_srt_content = item['content']
                        st.session_state.last_filename = item['filename']
                        if item.get('vtt_content'):
                            st.session_state.last_vtt_content = item['vtt_content']

                        # 자막 ID 저장
                        st.session_state.current_subtitle_id = item.get('id')
                        
                        # 관련 교정 로그가 있으면 로드
                        if item.get('id') in st.session_state.correction_logs_history:
                            st.session_state.correction_logs = st.session_state.correction_logs_history[item['id']].copy()
                        else:
                            # 로그가 없는 경우 빈 리스트로 초기화
                            st.session_state.correction_logs = []
                        
                        st.rerun()
                
                st.markdown("---")
    
    # 이전에 생성된 자막이 있으면 다운로드 버튼과 미리보기 버튼 표시
    if 'last_srt_content' in st.session_state and st.session_state.last_srt_content:
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            
            # 파일명 확인
            if 'last_filename' in st.session_state and st.session_state.last_filename:
                video_title = st.session_state.last_filename
                file_name_base = video_title.split('.')[0]
            else:
                video_title = "Unknown"
                file_name_base = "subtitle"
                
            # 영상 제목 표시
            with col1:
                st.info(f"이전에 생성된 자막: {video_title}")
            
            # SRT 다운로드 버튼
            with col2:
                st.download_button(
                    label="SRT 다운로드",
                    data=st.session_state.last_srt_content,
                    file_name=f"{file_name_base}.srt",
                    mime="text/plain",
                    use_container_width=True
                )
            
            # VTT 다운로드 버튼
            with col3:
                # SRT를 VTT로 변환
                if 'last_vtt_content' not in st.session_state or not st.session_state.last_vtt_content:
                    # SubtitleGenerator 객체가 있으면 그것을 사용, 없으면 임시로 생성
                    if 'subtitle_generator' in st.session_state and st.session_state.subtitle_generator:
                        generator = st.session_state.subtitle_generator
                    else:
                        generator = SubtitleGenerator(model_size="small")
                    
                    st.session_state.last_vtt_content = generator.convert_srt_to_vtt(st.session_state.last_srt_content)
                
                st.download_button(
                    label="VTT 다운로드",
                    data=st.session_state.last_vtt_content,
                    file_name=f"{file_name_base}.vtt",
                    mime="text/plain",
                    use_container_width=True
                )
            
            # 미리보기 버튼
            with col4:
                show_preview = st.button("미리보기", key="show_preview_button", use_container_width=True)
            
            # 미리보기 버튼이 클릭되면 자막 내용과 테이블 표시
            if show_preview:
                st.session_state.show_last_preview = True

                # 저장된 현재 자막 ID가 있으면 사용
                if 'current_subtitle_id' in st.session_state and st.session_state.current_subtitle_id:
                    current_id = st.session_state.current_subtitle_id
                    if current_id in st.session_state.correction_logs_history:
                        st.session_state.correction_logs = st.session_state.correction_logs_history[current_id].copy()
                else:
                    # 현재 자막의 ID 찾기
                    current_id = None
                    for item in st.session_state.subtitle_history:
                        if (item['filename'] == st.session_state.last_filename and 
                            item['content'] == st.session_state.last_srt_content):
                            current_id = item.get('id')
                            # ID를 찾았으면 해당 로그 불러오기
                            if current_id in st.session_state.correction_logs_history:
                                st.session_state.correction_logs = st.session_state.correction_logs_history[current_id].copy()
                                # 찾은 ID 저장
                                st.session_state.current_subtitle_id = current_id
                            break
            
            # 자막 미리보기 및 교정 로그를 하나의 화면에 표시
            if st.session_state.get('show_last_preview', False):
                # 미리보기 닫기 버튼
                if st.button("미리보기 닫기", key="hide_preview_button1"):
                    st.session_state.show_last_preview = False
                    st.rerun()  # 페이지 새로고침

                # 교정 로그가 있는 경우 표시
                if st.session_state.get('correction_logs') and len(st.session_state.correction_logs) > 0:
                    st.subheader("자막 교정 로그")
                    
                    # 교정 로그 표시 스타일
                    st.markdown("""
                    <style>
                    .log-container {
                        height: 400px;
                        overflow-y: auto;
                        background-color: #f0f2f6;
                        padding: 10px;
                        border-radius: 5px;
                        margin-bottom: 10px;
                        font-family: monospace;
                        border: 1px solid #ddd;
                    }
                    .original-subtitle {
                        color: #555;
                        margin-bottom: 4px;
                    }
                    .corrected-subtitle {
                        color: #0066cc;
                        margin-bottom: 12px;
                        font-weight: bold;
                    }
                    .error-message {
                        color: #cc0000;
                        font-weight: bold;
                    }
                    .log-divider {
                        border-bottom: 1px dashed #ccc;
                        margin: 8px 0;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    # 로그 표시
                    log_html = "<div class='log-container' id='log-container'>"
                    for i, log in enumerate(st.session_state.correction_logs):
                        if "원본 자막:" in log:
                            log_html += f"<div class='original-subtitle'>{log}</div>"
                        elif "교정된 자막:" in log:
                            log_html += f"<div class='corrected-subtitle'>{log}</div>"
                            if i < len(st.session_state.correction_logs) - 1:
                                log_html += "<div class='log-divider'></div>"
                        elif "오류" in log:
                            log_html += f"<div class='error-message'>{log}</div>"
                    log_html += "</div>"
                    
                    st.markdown(log_html, unsafe_allow_html=True)
                else:
                    st.info("이 자막에 대한 교정 로그가 없습니다.")

                with st.expander("자막 내용", expanded=True):
                    st.text_area("SRT 자막", st.session_state.last_srt_content, height=200)
                
                # 자막 미리보기 테이블
                st.subheader("자막 미리보기")
                srt_lines = st.session_state.last_srt_content.strip().split('\n\n')
                preview_data = []
                
                for block in srt_lines:
                    lines = block.split('\n')
                    if len(lines) >= 3:
                        try:
                            index = int(lines[0])
                            time_info = lines[1]
                            text = ' '.join(lines[2:])
                            preview_data.append({"번호": index, "시간": time_info, "자막": text})
                        except:
                            pass
                
                if preview_data:
                    st.dataframe(preview_data, use_container_width=True)
                
                # 미리보기 닫기 버튼
                if st.button("미리보기 닫기", key="hide_preview_button2"):
                    st.session_state.show_last_preview = False
                    st.rerun()  # 페이지 새로고침

    # 파일 업로드
    uploaded_file = st.file_uploader("음성 또는 영상 파일 업로드", type=["mp3", "wav", "mp4", "avi", "mov", "mkv"])
    
    if uploaded_file is not None:
        st.audio(uploaded_file, format="audio/wav")
        
        if st.button("자막 생성 시작", type="primary"):
            # 로그 초기화
            st.session_state.correction_logs = []

            # 프로그레스 바와 상태 텍스트
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            status_text.text("Whisper 모델 로딩 중...")
            
            # 자막 생성기 초기화
            generator = SubtitleGenerator(
                model_size=whisper_model,
                llm_provider=llm_provider
            )
            
            progress_bar.progress(10)
            status_text.text("자막 생성 중...")
            
            # 자막 생성
            srt_content = generator.generate_subtitles(
                audio_file=uploaded_file,
                progress_bar=progress_bar,
                status_text=status_text,
                language=lang_code,
                max_chars=max_chars,
                min_chars=min_chars,
                max_duration=max_duration,
                context=context,
                vad_enabled=vad_enabled,
                vad_aggressiveness=vad_aggressiveness
            )

            if srt_content:
                # 이전 자막을 히스토리에 저장 (기존 자막이 있는 경우)
                if st.session_state.last_srt_content is not None and st.session_state.last_filename is not None:
                    save_to_subtitle_history(
                        st.session_state.last_filename,
                        st.session_state.last_srt_content,
                        st.session_state.get('last_vtt_content'),
                        st.session_state.get('correction_logs', [])
                    )

                # 세션 상태에 자막 내용 저장
                st.session_state.last_srt_content = srt_content
                st.session_state.last_filename = uploaded_file.name
                st.session_state.last_vtt_content = generator.convert_srt_to_vtt(srt_content)

                # 새 자막을 히스토리에 저장하고 ID 바로 받기
                if st.session_state.get('correction_logs'):
                    new_subtitle_id = save_to_subtitle_history(
                        uploaded_file.name,
                        srt_content,
                        st.session_state.last_vtt_content,
                        st.session_state.correction_logs
                    )
                    
                    # ID를 세션 상태에 저장하여 미리보기 시 사용
                    if new_subtitle_id:
                        st.session_state.current_subtitle_id = new_subtitle_id

                # 자막과 교정 로그를 연결하여 저장
                if len(st.session_state.get('correction_logs', [])) > 0:
                    # 방금 생성한 자막 찾기
                    for item in reversed(st.session_state.subtitle_history):
                        if (item['filename'] == uploaded_file.name and 
                            item['content'] == srt_content):
                            # 교정 로그 저장
                            st.session_state.correction_logs_history[item['id']] = st.session_state.correction_logs.copy()
                            break
                
                # 자막 생성기 저장 (나중에 VTT 변환 등에 사용)
                if 'subtitle_generator' not in st.session_state:
                    st.session_state.subtitle_generator = generator

                # 자막 표시
                st.subheader("생성된 자막")
                st.text_area("SRT 자막", srt_content, height=300)
                
                # 다운로드 버튼들
                file_name_base = uploaded_file.name.split('.')[0]
                
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.write("")  # 빈 공간
                
                with col2:
                    st.download_button(
                        label="SRT 파일 다운로드",
                        data=srt_content,
                        file_name=f"{file_name_base}.srt",
                        mime="text/plain",
                        use_container_width=True
                    )
                
                with col3:
                    st.download_button(
                        label="VTT 파일 다운로드",
                        data=st.session_state.last_vtt_content,
                        file_name=f"{file_name_base}.vtt",
                        mime="text/plain",
                        use_container_width=True
                    )
                
                # 미리보기 탭 추가
                st.subheader("자막 미리보기")
                
                # SRT 파싱
                srt_lines = srt_content.strip().split('\n\n')
                preview_data = []
                
                for block in srt_lines:
                    lines = block.split('\n')
                    if len(lines) >= 3:
                        try:
                            index = int(lines[0])
                            time_info = lines[1]
                            text = ' '.join(lines[2:])
                            preview_data.append({"번호": index, "시간": time_info, "자막": text})
                        except:
                            pass
                
                if preview_data:
                    st.dataframe(preview_data, use_container_width=True)

if __name__ == "__main__":
    main()