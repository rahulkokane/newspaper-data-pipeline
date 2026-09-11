# The Hindu E-paper local pipeline

## V2 extraction approach

The article extractor uses PDF text **blocks + coordinates** instead of flattening the whole page into a text stream. This is important because newspaper pages use multiple independent columns, sidebars, captions, decks and photos.

For each page it:

1. extracts text blocks with x/y coordinates and font sizes;
2. detects likely article headlines from font/layout signals;
3. maps a headline to the newspaper's vertical column grid;
4. finds the next headline occupying the same columns as the article boundary;
5. extracts body blocks only inside those columns;
6. identifies/removes bylines, locations and photo captions;
7. reconstructs reading order column-by-column;
8. reports simple extraction-quality signals.

The extractor is still heuristic. Newspaper layouts are complex, so the next step after V2 is to build a page-layout test suite and tune against several representative pages before adding AI.

## Run

```powershell
python -m pip install -r requirements.txt
python main.py
python extract.py
python download_test.py --from 2026-07-01 --to 2026-07-31 --delay 15
```

extract.py is to extract data from pdf
src/article_extractor are fun to extract articles
download_test is our main scraper


