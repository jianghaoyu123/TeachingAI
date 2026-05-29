from __future__ import annotations

GRADE_BAND_PRIMARY_LOWER = "primary_lower"
GRADE_BAND_PRIMARY_UPPER = "primary_upper"
GRADE_BAND_JUNIOR_7 = "junior_7"
GRADE_BAND_JUNIOR_8 = "junior_8"
GRADE_BAND_JUNIOR_9 = "junior_9"
GRADE_BAND_SENIOR_10 = "senior_10"
GRADE_BAND_SENIOR_11 = "senior_11"
GRADE_BAND_SENIOR_12 = "senior_12"

GRADE_TO_BAND: dict[str, str] = {
    "一年级": GRADE_BAND_PRIMARY_LOWER,
    "二年级": GRADE_BAND_PRIMARY_LOWER,
    "三年级": GRADE_BAND_PRIMARY_UPPER,
    "四年级": GRADE_BAND_PRIMARY_UPPER,
    "五年级": GRADE_BAND_PRIMARY_UPPER,
    "六年级": GRADE_BAND_PRIMARY_UPPER,
    "七年级": GRADE_BAND_JUNIOR_7,
    "八年级": GRADE_BAND_JUNIOR_8,
    "九年级": GRADE_BAND_JUNIOR_9,
    "初一": GRADE_BAND_JUNIOR_7,
    "初二": GRADE_BAND_JUNIOR_8,
    "初三": GRADE_BAND_JUNIOR_9,
    "高一": GRADE_BAND_SENIOR_10,
    "高二": GRADE_BAND_SENIOR_11,
    "高三": GRADE_BAND_SENIOR_12,
}

BAND_LABELS: dict[str, str] = {
    GRADE_BAND_PRIMARY_LOWER: "小学低段（一至二年级）",
    GRADE_BAND_PRIMARY_UPPER: "小学中高段（三至六年级）",
    GRADE_BAND_JUNIOR_7: "初一（七年级）·深圳",
    GRADE_BAND_JUNIOR_8: "初二（八年级）·深圳",
    GRADE_BAND_JUNIOR_9: "初三（九年级）·深圳",
    GRADE_BAND_SENIOR_10: "高一·深圳",
    GRADE_BAND_SENIOR_11: "高二·深圳",
    GRADE_BAND_SENIOR_12: "高三·深圳",
}

JUNIOR_BANDS = (GRADE_BAND_JUNIOR_7, GRADE_BAND_JUNIOR_8, GRADE_BAND_JUNIOR_9)
SENIOR_BANDS = (GRADE_BAND_SENIOR_10, GRADE_BAND_SENIOR_11, GRADE_BAND_SENIOR_12)


def resolve_grade_band(grade: str) -> str:
    return GRADE_TO_BAND.get(grade.strip(), GRADE_BAND_JUNIOR_8)