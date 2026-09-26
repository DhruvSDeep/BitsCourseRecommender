import numpy as np
import pandas as pd
import pdfplumber


def bulletinParser():
  rows = []
  bulletinpdf = "dataset/bulletin.pdf"
  target_page = 209
  page_index = target_page - 1

  with pdfplumber.open(bulletinpdf) as pdf:
    if page_index >= len(pdf.pages):
      return

    page = pdf.pages[page_index]

    tables = page.extract_tables({
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
    })

    for table in tables:
      for row in table:
        cleaned_row = [" ".join(cell.split()) if cell else "" for cell in row]

        row_text = " ".join(cleaned_row).upper()
        if not row_text.strip():
          continue

        rows.append(cleaned_row)

  if not rows:
    return

  headers = [col if col else f"COL_{i}" for i, col in enumerate(rows[0])]
  data_rows = rows[1:]

  df = pd.DataFrame(data_rows, columns=headers)
  df.replace("", None, inplace=True)
  df = df.fillna("")

  df.to_csv("dataset/bulletin_requirements.csv", index=False)


def bulletinCourseStructure():
  rows = []
  bulletinpdf = "dataset/bulletin.pdf"
  page_range = range(211, 314)  # 211 to 313 inclusive

  with pdfplumber.open(bulletinpdf) as pdf:
    total_pages = len(pdf.pages)

    for page_num in page_range:
      page_index = page_num - 1
      if page_index >= total_pages:
        continue

      page = pdf.pages[page_index]

      tables = page.extract_tables({
          "vertical_strategy": "lines",
          "horizontal_strategy": "lines",
          "snap_tolerance": 3,
      })

      for table in tables:
        for row in table:
          cleaned_row = [" ".join(cell.split()) if cell else "" for cell in row]

          row_text = " ".join(cleaned_row).upper()
          if not row_text.strip():
            continue

          rows.append(cleaned_row)

  if not rows:
    return

  raw_headers = rows[0]
  headers = [
      col if col else f"COL_{i+1}" for i, col in enumerate(raw_headers)
  ]
  col_count = len(headers)

  data_rows = []
  for row in rows[1:]:
    if row == raw_headers:
      continue

    # Align row dimensions to header width
    if len(row) < col_count:
      row += [""] * (col_count - len(row))
    elif len(row) > col_count:
      row = row[:col_count]

    data_rows.append(row)

  df = pd.DataFrame(data_rows, columns=headers)
  df.replace("", None, inplace=True)
  df = df.fillna("")

  df.to_csv("dataset/bulletin_p211_313_clean.csv", index=False)

#bulletinCourseStructure()
bulletinParser()