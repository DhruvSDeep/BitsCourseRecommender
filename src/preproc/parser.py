import pdfplumber
import pandas as pd
import numpy as np

def timetableParser():
    rows = []
    timetablepdf = "dataset/timetable.pdf"
    page_range = range(10, 113)      #10-112
    columns = [
    "COM_COD", "COURSE_NO", "COURSE_TITLE",
    "L", "P", "T", "S", "U_C_H",
    "SEC", "INSTRUCTOR", "ROOM", "DAYS_HOURS",
    "MIDSEM_SLOT", "COMPRE_SLOT"]

    
    with pdfplumber.open(timetablepdf) as pdf:
            for page_num in page_range:
                page_index = page_num - 1
                page = pdf.pages[page_index]


                tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 3})
                
                for table in tables:
                    for row in table:
                        #clean whitespace and all
                        cleaned_row = [
                            " ".join(cell.split()) if cell else "" for cell in row]

                        if len(cleaned_row) < len(columns):
                            cleaned_row += [""] * (len(columns) - len(cleaned_row))
                        elif len(cleaned_row) > len(columns):
                            cleaned_row = cleaned_row[:len(columns)]

                        row_text = " ".join(cleaned_row).upper()
                        if not row_text.strip():
                            continue
                        if any(kw in row_text for kw in ["COM COD", "COURSE NO", "COURSE TITLE", "COURSEWISE TIMETABLE", "FIRST SEMESTER", "SECOND SEMESTER", "NOTE:", "NOTE."]):
                            continue
                        if len(cleaned_row) > 5 and cleaned_row[3] == "L" and cleaned_row[4] == "P" and cleaned_row[5] == "T":
                            continue

                        rows.append(cleaned_row)
                
    df = pd.DataFrame(rows, columns=columns)

    df.replace("", None, inplace=True)


    fill_cols = ["COM_COD", "COURSE_NO", "COURSE_TITLE", "U_C_H"]
    df[fill_cols] = df[fill_cols].ffill()

    df = df.dropna(subset=["SEC", "INSTRUCTOR", "ROOM"], how="all")

    df = df.fillna("")

    df = df.drop(columns=['L', 'P', 'T', 'S', 'ROOM', 'INSTRUCTOR'])
    df = df.rename(columns={
    "COM_COD": "COURSE_CODE",
    "U_C_H": "CREDITS",
    "COURSE_NO": "COURSE_NUM",
    "DAYS_HOURS": "SCHEDULE"})


    df.to_csv("dataset/timetable_clean.csv", index=False)




timetableParser()