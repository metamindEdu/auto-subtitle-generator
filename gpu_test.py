import torch

def check_gpu():
    if torch.cuda.is_available():
        print("GPU 사용 가능:")
        print(f"- GPU 모델: {torch.cuda.get_device_name(0)}")
        print(f"- CUDA 버전: {torch.version.cuda}")
    else:
        print("GPU를 사용할 수 없습니다. CPU만 사용 가능합니다.")

if __name__ == "__main__":
    check_gpu()