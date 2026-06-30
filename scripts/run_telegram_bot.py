from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.telegram_bot import run_polling


if __name__ == "__main__":
    run_polling()
