import pandas as pd

# Load the provided Excel file
file_path = 'G:/LabInventory/BoM报价-立创_20260212.xlsx'  # 修改为你的文件路径
excel_data = pd.ExcelFile(file_path)

# Load the sheet and skip the first 5 rows (since headers start from row 6)
df = pd.read_excel(excel_data, sheet_name='sheet', header=5)  # header=5 跳过前五行

# Extract the column headers and clean them
headers = df.columns.tolist()

# Selecting specific headers based on the provided request
target_headers = [
    'ID', 'Name', 'Manufacturer Part', 'Designator', 'Footprint 封装', 'Footprint', 'Quantity', 'Manufacturer Part',
    'Manufacturer', 'Supplier', 'Supplier Part', '匹配结果', '商品名称', '型号', 'Manufacturer Part', '品牌',
    'Manufacturer', '封装', 'Footprint', '参数', '目录', '商品编号', '商品链接', '渠道', '交期', 'MOQ', 'MPQ',
    '库存', '购买数量', '单价(RMB)', '关税', '小计(RMB)', '备注', '匹配结果', '商品名称', '匹配结果', '商品名称',
    '型号', '品牌', '封装', '参数', '目录', '商品编号', '商品链接', '渠道', '交期', 'MOQ', 'MPQ', '库存',
    '购买数量', '单价(RMB)', '关税', '小计(RMB)', '备注'
]

# Filtering headers that match the target list
filtered_headers = [header for header in headers if header in target_headers]

# Extract corresponding rows (skip the first 5 rows and keep the remaining data)
data_rows = df[filtered_headers].dropna(how="all")  # drop rows where all cells are NaN

# Save the headers and the corresponding data rows to a text file
output_file = "parts_data.txt"
with open(output_file, "w", encoding="utf-8") as file:
    # Write headers
    file.write("\t".join(filtered_headers) + "\n")
    # Write data rows
    for _, row in data_rows.iterrows():
        file.write("\t".join(str(val) for val in row) + "\n")

print(f"Data has been saved to {output_file}")