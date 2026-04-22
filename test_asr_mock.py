from providers.mock_asr_provider import MockASRProvider

def main():
    asr = MockASRProvider()
    result = asr.transcribe("sample.wav")
    print(result)

if __name__ == "__main__":
    main()