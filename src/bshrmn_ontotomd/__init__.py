from .models import LoggingParamsConfig, GlobalParamsConfig, PreloadConfig, ProcessConfig
from .ontotomd import preload_ontos, process_onto, OTMProcessSummary

def main() -> None:
    print("Hello from bshrmn-ontotomd!")
