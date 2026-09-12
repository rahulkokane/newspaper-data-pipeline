# The Hindu E-paper local pipeline

## Run

```powershell
python -m pip install -r requirements.txt
python main.py
python extract.py
python download_test.py --from 2026-07-01 --to 2026-07-31 --delay 15
```

To start session on chrome;
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="D:\Downloads\hindu_pipeline_v2\hindu_pipeline_v2\.hindu-debug-profile"
```

extract.py is to extract data from pdf.\
src/article_extractor are fun to extract articles.\
download_test is our main scraper.\


