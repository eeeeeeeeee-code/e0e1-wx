# -*- coding: utf-8 -*-

import pandas as pd


class Process_Print:
    def __init__(self, file_path):
        self.file_path = file_path

    def three_process_fuzz(self, data):
        series_data = pd.Series(data)
        df = pd.DataFrame({'接口': series_data})
        try:
            with pd.ExcelWriter(self.file_path, engine="openpyxl", mode='a') as writer:
                df.to_excel(writer, sheet_name='拼接', index=False)
        except FileNotFoundError:
            with pd.ExcelWriter(self.file_path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name='拼接', index=False)

    def all_xlsx_file(self, data, columns_name, sheet_name):
        df = pd.DataFrame.from_records(data)
        df.columns = columns_name
        with pd.ExcelWriter(self.file_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    def add_xlsx_file(self, data, columns_name, sheet_name):
        df = pd.DataFrame.from_records(data)
        df.columns = columns_name
        try:
            with pd.ExcelWriter(self.file_path, engine="openpyxl", mode='a') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        except FileNotFoundError:
            with pd.ExcelWriter(self.file_path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)