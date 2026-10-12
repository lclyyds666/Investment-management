"""Excel template generation and parsing for operation forecast factors."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import ValidationError

from app.schemas.operation_forecast import (
    ForecastFactor,
    ForecastFactorParseResult,
    ForecastFactorRowError,
)

FACTOR_HEADERS = [
    "开始日期",
    "结束日期",
    "景区",
    "业务类型",
    "平台",
    "因素类型",
    "因素名称",
    "影响比例",
    "备注",
]
MAX_FACTOR_ROWS = 1000
MAX_FACTOR_FILE_SIZE = 5 * 1024 * 1024


def build_factor_template() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "预测影响因素"
    sheet.append(FACTOR_HEADERS)
    sheet.append(["2026-11-01", "2026-11-03", "", "ticket", "抖音", "天气", "雨天", "-10%", "空景区或平台表示全部"])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    widths = [14, 14, 18, 14, 16, 14, 22, 14, 32]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return _text(value)


def _impact_rate(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, str):
        normalized = value.strip()
        percentage = normalized.endswith("%")
        if percentage:
            normalized = normalized[:-1].strip()
        try:
            result = Decimal(normalized)
        except InvalidOperation as error:
            raise ValueError("影响比例格式错误") from error
        return result / Decimal("100") if percentage else result
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("影响比例格式错误") from error


def _map_factor_row(values) -> dict:
    padded = list(values[: len(FACTOR_HEADERS)]) + [None] * (len(FACTOR_HEADERS) - len(values))
    return {
        "start_date": _date_value(padded[0]),
        "end_date": _date_value(padded[1]),
        "scenic_id": _text(padded[2]),
        "business_type": _text(padded[3]),
        "platform": _text(padded[4]),
        "factor_type": _text(padded[5]),
        "name": _text(padded[6]),
        "impact_rate": _impact_rate(padded[7]),
        "remark": _text(padded[8]),
    }


def _validation_message(error: ValidationError) -> str:
    return "；".join(item["msg"] for item in error.errors(include_url=False))


def parse_factor_workbook(content: bytes) -> ForecastFactorParseResult:
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as error:
        raise ValueError("无法读取 Excel 文件") from error

    try:
        rows = workbook.active.iter_rows(values_only=True)
        headers = next(rows, None)
        if headers is None or [_text(value) for value in headers] != FACTOR_HEADERS:
            raise ValueError(f"表头必须为：{'、'.join(FACTOR_HEADERS)}")

        data_rows = [
            (row_no, values)
            for row_no, values in enumerate(rows, start=2)
            if any(value not in (None, "") for value in values)
        ]
        if len(data_rows) > MAX_FACTOR_ROWS:
            raise ValueError(f"数据行不能超过 {MAX_FACTOR_ROWS} 行")

        items = []
        errors = []
        for row_no, values in data_rows:
            try:
                items.append(ForecastFactor.model_validate(_map_factor_row(values)))
            except ValidationError as error:
                errors.append(ForecastFactorRowError(row_no=row_no, message=_validation_message(error)))
            except ValueError as error:
                errors.append(ForecastFactorRowError(row_no=row_no, message=str(error)))
        return ForecastFactorParseResult(items=items, errors=errors)
    finally:
        workbook.close()
