import os
import subprocess
import whisper
import pysrt
import webrtcvad
import collections
import contextlib
import wave
import numpy as np
import soundfile as sf
import warnings
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
            print(f"프롬프트 파일 로드 중 오류 발생 ({filename}): {str(e)}")
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
    def __init__(self, model_size="small", llm_provider="openai", prompts_dir="prompts"):
        print("Whisper 모델 로딩 중...")
        self.model = whisper.load_model(model_size)
        print("모델 로딩 완료!")
        
        self.llm_provider = llm_provider
        self.prompt_manager = PromptManager(prompts_dir)
        
        if llm_provider == "openai":
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if openai_api_key:
                self.llm_client = OpenAI(api_key=openai_api_key)
            else:
                print("WARNING: OPENAI_API_KEY가 .env 파일에 설정되지 않았습니다.")
                self.llm_client = None
        elif llm_provider == "anthropic":
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
            if anthropic_api_key:
                self.llm_client = anthropic.Anthropic(api_key=anthropic_api_key)
            else:
                print("WARNING: ANTHROPIC_API_KEY가 .env 파일에 설정되지 않았습니다.")
                self.llm_client = None
        else:
            self.llm_client = None

    def get_duration(self, input_path):
        """파일의 재생 시간을 가져옴"""
        ffmpeg_path = r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"
        probe_cmd = [ffmpeg_path, '-i', input_path]
        try:
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, encoding='utf-8')
            for line in probe_result.stderr.split('\n'):
                if "Duration:" in line:
                    duration_str = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = map(float, duration_str.split(':'))
                    total_seconds = h * 3600 + m * 60 + s
                    return total_seconds, duration_str
        except Exception as e:
            print(f"Duration 확인 중 오류: {str(e)}")
        return None, None
    
    def convert_to_wav(self, input_path, output_path):
        """영상/음성 파일을 WAV 형식으로 변환"""
        total_seconds, duration_str = self.get_duration(input_path)
        if duration_str:
            print(f"파일 길이: {duration_str}")
        
        ffmpeg_path = r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"
        command = [
            ffmpeg_path,
            '-i', input_path,
            '-ar', '16000',
            '-ac', '1',
            '-c:a', 'pcm_s16le',
            output_path
        ]
        print("\n오디오 변환 중...")
        print(f"실행할 명령어: {' '.join(command)}")
        
        result = subprocess.run(command, check=True, encoding='utf-8')
        return output_path, total_seconds

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
                if not hasattr(self, '_max_chars') or len(current.text + " " + next_sub.text) <= self._max_chars:
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
            print("\n" + "="*50)
            print(f"원본 자막: {subtitle_text}")
            
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
            
            print(f"교정된 자막: {corrected_text}")
            print("="*50)
            
            return corrected_text
                
        except Exception as e:
            print(f"자막 교정 중 오류 발생: {str(e)}")
            return subtitle_text

    def generate_subtitles(self, audio_path, output_path=None, language=None, max_chars=None, min_chars=None, max_duration=None, context=None):
        """자막 생성 함수"""
        if output_path is None:
            base_path = os.path.splitext(audio_path)[0]
            output_path = f"{base_path}.srt"
        
        wav_path = os.path.splitext(audio_path)[0] + '_temp.wav'
        try:
            # WAV 파일 생성
            wav_path, total_seconds = self.convert_to_wav(audio_path, wav_path)
            print(f"\nWAV 파일 생성됨: {wav_path}")
            
            # VAD를 사용하여 음성 구간 감지
            print("\n음성 구간 감지 중...")
            voice_segments = process_with_vad(wav_path)
            print(f"감지된 음성 구간: {len(voice_segments)}개")
            
            # 전체 자막 정보 저장용
            all_segments = []
            current_position = 0
            
            # 오디오 파일 로드
            audio, sample_rate = sf.read(wav_path)
            audio = audio.astype(np.float32)
            
            print("\n음성 인식 시작...")
            for i, (start, end) in enumerate(voice_segments):
                print(f"\n음성 구간 {i+1}/{len(voice_segments)} 처리 중...")
                
                # 현재 구간의 오디오 추출
                start_sample = int(start * sample_rate)
                end_sample = int(end * sample_rate)
                segment_audio = audio[start_sample:end_sample]
                
                # Whisper로 음성 인식
                result = self.model.transcribe(segment_audio, language=language if language else None)
                
                # 세그먼트 시간 조정
                for segment in result["segments"]:
                    segment["start"] = start + segment["start"]
                    segment["end"] = start + segment["end"]
                    all_segments.append(segment)
            
            print("\n자막 파일 생성 중...")
            subs = pysrt.SubRipFile()
            subtitle_index = 1
            
            # 디버깅을 위한 파일 저장
            # raw_text_path = os.path.splitext(audio_path)[0] + '_raw.txt'
            # with open(raw_text_path, 'w', encoding='utf-8') as f:
            #     full_text = " ".join(seg["text"].strip() for seg in all_segments)
            #     f.write(full_text)
            
            # segment_path = os.path.splitext(audio_path)[0] + '_segments.txt'
            # with open(segment_path, 'w', encoding='utf-8') as f:
            #     for segment in all_segments:
            #         f.write(f"{segment['start']:.2f} - {segment['end']:.2f}: {segment['text']}\n")
            
            # 자막 생성
            for i, segment in enumerate(all_segments):
                # 이전/다음 자막 컨텍스트 수집
                previous_subs = [seg["text"].strip() for seg in all_segments[max(0, i-2):i]]
                next_subs = [seg["text"].strip() for seg in all_segments[i+1:i+3]]
                
                # LLM으로 자막 교정
                if self.llm_client:
                    print(f"\n[자막 #{i+1}/{len(all_segments)}] LLM 교정 중...")
                    text = self.correct_subtitle_with_llm(
                        segment["text"].strip(), context, previous_subs, next_subs
                    )
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
                merged_subs = self.merge_short_subtitles(subs, min_chars)
                subs = pysrt.SubRipFile()
                for sub in merged_subs:
                    subs.append(sub)
            
            subs.save(output_path, encoding='utf-8')
            print(f"자막 파일이 생성되었습니다: {output_path}")
            
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)
                print("임시 파일 정리 완료")
        
        return output_path

def main():
    print("자막 생성을 시작합니다...")
    
    # LLM 제공자 선택
    while True:
        llm_provider = input("사용할 LLM 제공자를 선택하세요 (1: OpenAI GPT-4, 2: Anthropic Claude, 3: 사용안함): ").strip()
        if llm_provider == "1":
            llm_provider = "openai"
            break
        elif llm_provider == "2":
            llm_provider = "anthropic"
            break
        elif llm_provider == "3":
            llm_provider = None
            break
        else:
            print("잘못된 선택입니다. 다시 선택해주세요.")
    
    generator = SubtitleGenerator(
        model_size="small",
        llm_provider=llm_provider
    )
    
    # 파일 경로 설정
    file_path = input("처리할 파일 경로를 입력하세요: ").strip('"')  # 따옴표 제거
    
    # 옵션 설정
    max_chars = input("한 자막당 최대 글자 수를 입력하세요 (기본값: 제한 없음): ").strip()
    max_chars = int(max_chars) if max_chars.isdigit() else None
    
    max_duration = input("한 자막당 최대 시간(초)을 입력하세요 (기본값: 제한 없음): ").strip()
    max_duration = float(max_duration) if max_duration.replace('.', '').isdigit() else None
    
    min_chars = input("한 자막당 최소 글자 수를 입력하세요 (기본값: 제한 없음): ").strip()
    min_chars = int(min_chars) if min_chars.isdigit() else None
    
    language = input("자막 언어를 입력하세요 (ko: 한국어, en: 영어, 기본값: 자동 감지): ").strip()
    language = language if language else None
    
    context = input("영상의 컨텍스트를 입력하세요 (예: 교육 영상, 독해력 강의 등): ").strip()
    context = context if context else None
    
    if os.path.exists(file_path):
        print(f"파일을 찾았습니다: {file_path}")
        try:
            output_path = generator.generate_subtitles(
                audio_path=file_path,
                language=language,
                max_chars=max_chars,
                max_duration=max_duration,
                min_chars=min_chars,
                context=context
            )
            print(f"\n작업이 완료되었습니다!")
            print(f"생성된 자막 파일: {output_path}")
        except Exception as e:
            print(f"\n오류가 발생했습니다: {str(e)}")
            import traceback
            traceback.print_exc()
    else:
        print(f"파일을 찾을 수 없습니다: {file_path}")

if __name__ == "__main__":
    main()