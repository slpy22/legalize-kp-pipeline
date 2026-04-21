# legalize-kp-pipeline

북한 법령 텍스트를 Markdown+YAML로 변환하고 Git 히스토리를 생성하는 파이프라인.

## 실행
pip install -r requirements.txt
python main.py
python main.py --skip-git  # Git 없이 파일만 생성

## 테스트
python -m pytest tests/ -v
