# SFT 数据集质量检查工具

可安装的 Python CLI，检查 UTF-8 JSONL / CSV 数据集，生成含错误行号的 JSON 报告。需要 Python 3.10+，运行和测试均不依赖第三方库。

## 安装

在项目目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
sft-check --help
```

构建使用 setuptools 和 wheel，pip 默认在隔离环境中安装构建依赖。如果离线环境已安装这两项，可使用 `python -m pip install --no-build-isolation .`。开发时可用 `python -m pip install -e .` 安装。

## 使用

```bash
sft-check sample.jsonl
sft-check sample.jsonl --output report.json
python -m sft_checker sample.jsonl
sft-check sample_csv.csv --export-valid sample_csv.valid.jsonl
sft-check sample.jsonl --export-valid sample.valid.jsonl
```

默认报告位于输入文件所在目录，命名为 `<文件名去掉扩展名>.report.json`；示例生成项目根目录的 `sample.report.json`。`-o/--output` 可指定路径，其父目录必须已存在。同名旧报告会被原子替换；禁止报告覆盖输入文件（包括符号链接、硬链接）。

退出码：`0` 表示全部通过（包含空文件）；`1` 表示检查完成但存在无效记录，报告仍然生成；`2` 表示参数或文件读写失败。自动化脚本中请区别数据问题与程序失败。

## 检查规则与统计口径

- JSONL 每个物理行是一条待检查数据，行号从 1 开始，空行计为格式错误；末尾换行不额外算一行。支持 CRLF、文件开头的 UTF-8 BOM、末行无换行。
- JSONL 每行必须是 JSON 对象，包含 `instruction`、`input`、`output` 三个字符串字段。允许空字符串和额外字段。
- 缺失字段为 `missing_field`；非字符串字段为 `invalid_type`；JSON 语法、非对象值、无效 UTF-8、重复 JSON 键、NaN/Infinity 等错误为 `invalid_format`。
- 仅对结构合格的记录去重，比较三个字段解析后的字符串值，忽略键顺序和额外字段。不裁剪空白或做大小写、Unicode 归一化。首次出现为有效，其后每次出现记为 `duplicate_record`，说明中引用首次出现行号。
- 一行可以有多条错误，但只计一次无效记录。`errors` 的长度可能大于无效记录数。
- 完整扫描后 `total_lines == checked_lines == valid_records + invalid_records`。格式错误不会中断后续检查；文件读写失败不生成新的完整报告。

报告结构示意：

```json
{
  "total_lines": 2,
  "checked_lines": 2,
  "valid_records": 1,
  "invalid_records": 1,
  "errors": [
    {"line_number": 2, "issue_type": "missing_field", "description": "缺少必需字段：output"}
  ]
}
```

逐行读取避免一次性加载源文件；精确去重需要保存唯一记录的三个字段，报告保存全部错误，因此内存占用随唯一数据和错误数量增长。本工具检查结构与重复，不评价答案事实性或内容语义。

## 项目结构

```text
pyproject.toml             包元数据与 CLI 入口
src/sft_checker/
  __init__.py             导出 check_file API
  __main__.py             python -m 入口
  cli.py                  参数解析与退出码
  readers.py              按扩展名选择 JSONL / CSV 解析器
  checker.py              共用字段校验、去重与流式导出
  models.py               报告数据模型
  reporting.py            共用原子写入与路径冲突保护
tests/test_checker.py     第一阶段 15 项回归测试
tests/test_csv_export.py  第二阶段 17 项新增测试
sample_csv.csv            CSV 混合测试数据
sample.jsonl              10 行混合测试数据
sample.report.json        实际运行生成的报告
```

## 测试

安装后执行：

```bash
python -m unittest discover -s tests -v
```

测试覆盖示例统计、缺失字段、多问题计数、精确去重、类型校验、严格 JSON、空文件、编码异常、BOM/CRLF、CLI 退出码、报告路径以及输入覆盖保护。示例预期为总行数 10、已检查 10、有效 3、无效 7，共 8 条问题。

## 第一阶段实际验证（历史）

本环境系统 Python 3.12 没有 pip，使用已有的 Miniconda Python 3.13.2 和构建工具完成离线构建与安装：

```bash
/home/emily/miniconda3/bin/python -m venv --system-site-packages .venv
.venv/bin/python -m pip install --no-build-isolation --no-deps .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/sft-check sample.jsonl
```

- 成功构建并安装 `sft-quality-checker 0.1.0`，安装命令退出码为 0。
- 实际执行 15 项测试，全部通过（`Ran 15 tests ... OK`），测试命令退出码为 0。
- 示例运行输出：`检查完成：总行数=10，已检查=10，有效=3，无效=7`，退出码为 1，生成 `sample.report.json`，包含 8 条问题。
- 在项目之外的 `/tmp` 运行安装后的 `sft-check --help` 成功，退出码为 0。

## CSV 格式与位置约定

- 根据扩展名自动选择解析器，支持 `.jsonl`、`.csv`，不区分大小写。其他扩展名返回退出码 2，无需也不提供手工格式参数。
- CSV 使用逗号分隔，首条记录为表头，列名按原样匹配；必需列为 `instruction,input,output`，允许额外列和调整列序。
- 所有单元格均按字符串处理，包括数字、`true`、`null` 等文本；显式空单元格是合法空字符串。短行导致必需字段没有对应单元格时，报告 `missing_field`。缺少额外字段不影响必需字段检查。
- 缺少必需表头列时，每条数据记录报告 `missing_field`；重复表头列名、空行、列数过多或解析失败报告 `invalid_format`。表头不合法且没有数据记录时，在第 1 行报告一条无效检查项，可包含多个问题；合法表头但无数据或空文件计为 0 条。
- 支持 UTF-8 BOM、CRLF、带引号的逗号、双引号转义与跨行单元格。错误的 `line_number` 是记录起始的物理行号，包含表头占用的行；重复说明引用首次有效记录的物理行号。
- CSV 的 `total_lines` 和 `checked_lines` 沿用原字段名，表示数据逻辑记录数量，正常表头不计数；跨多行的记录只计一次。因此两者仍等于有效与无效记录数之和，但不等于 CSV 物理行数。JSONL 的原有统计口径不变。
- 使用标准库 CSV 严格解析；未闭合引号可能将后续多行吸收为一条损坏记录，此时在起始行报告错误，不推测无法确定的记录边界。

## 导出有效数据

`--export-valid PATH` 是可选参数；不指定时仍只生成检查报告。无论输入是 CSV 还是 JSONL，导出均为 UTF-8 JSONL，每条有效记录占一行，保留原顺序、字段值及额外字段。去重仅比较三个必需字段，保留第一条符合规则的记录。没有有效数据时生成空文件。

导出边检查边写入临时文件，成功后原子替换指定目标。目标父目录必须存在，已有目标会被替换。输入、报告和导出路径不能互相重合，包括符号链接与硬链接。不支持的格式或读取失败不会替换已有导出文件。报告与导出分别提交，非跨文件事务：若导出成功后报告写入失败，退出码为 2，但导出文件可能已经保存。

API 保持原有 `check_file(path) -> Report` 调用兼容，并新增可选参数：

```python
from sft_checker import check_file
report = check_file("sample_csv.csv", export_valid="valid.jsonl")
```

## 第二阶段实际验证

在现有虚拟环境安装更新后的 0.2.0：

```bash
.venv/bin/python -m pip install --no-build-isolation --no-deps --no-cache-dir .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/sft-check sample.jsonl --export-valid sample.valid.jsonl
.venv/bin/sft-check sample_csv.csv --export-valid sample_csv.valid.jsonl
```

- 修改前运行第一阶段原有 15 项测试，全部通过。
- 修改后运行原有 15 项和新增 17 项测试，共 **32 项全部通过**，退出码 0。
- JSONL 示例：10 条，有效 3、无效 7，导出 3 条；原有检查结果保持不变。
- CSV 示例：6 条数据记录（不含表头），有效 3、无效 3，导出 3 条。
- 两次示例检查均返回 1（含无效数据），报告分别为 `sample.report.json`、`sample_csv.report.json`。
- 在 `/tmp` 使用安装后的 CLI 再次检查两份导出 JSONL，均返回 0，全部 3 条有效。

新增测试覆盖自动识别与大小写扩展名、字符串值、缺失字段、重复列名、列数异常、空数据、编码错误、跨行位置、JSONL/CSV 去重导出、额外字段保留、输出失败以及同路径/链接覆盖保护。

可分发 wheel 为 `dist/sft_quality_checker-0.2.0-py3-none-any.whl`，安装命令：

```bash
python -m pip install dist/sft_quality_checker-0.2.0-py3-none-any.whl
```
