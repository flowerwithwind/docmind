"""抽取服务单元测试（M4/FR-06）：规则抽取器 / 数值归一化 / JSON 解析 / 分批。"""

from __future__ import annotations

from app.fallback.extractor import _cn_num_to_float, extract_by_rules
from app.seed import CONTRACT_FIELDS, FINANCIAL_FIELDS
from app.services.extraction import _batches, _parse_json
from app.utils.text import normalize_value


def _text_chunk(content: str, title: str = "", cid: int = 1) -> dict:
    return {
        "id": cid,
        "kind": "text",
        "content": content,
        "title": title,
        "section_path": "",
        "page": 1,
    }


def _table_chunk(content: str, cid: int = 1) -> dict:
    return {
        "id": cid,
        "kind": "table",
        "content": content,
        "title": "表格",
        "section_path": "",
        "page": 1,
    }


# 与 tests/helpers.py CONTRACT_PARAGRAPHS 分块后的内容保持一致
CONTRACT_CHUNK_1 = _text_chunk(
    "合同名称：产品购销合同\n甲方：华信科技有限公司\n乙方：远景供应链有限公司\n"
    "签订日期：2026年3月15日\n合同金额：人民币壹佰贰拾万元整，币种为人民币。",
    title="第一条 当事人",
)
CONTRACT_CHUNK_2 = _text_chunk(
    "付款方式：预付款30%，验收合格后70%。\n交付期限：合同签订后30日内交货。\n"
    "违约金条款：逾期每日按合同金额的0.5%支付违约金。\n"
    "争议解决：双方争议提交甲方所在地人民法院诉讼解决。\n"
    "有效期：本合同自签订之日起一年。",
    title="第二条 付款与交付",
)


# ---------------------------------------------------------------- 中文数字

def test_cn_num_to_float():
    assert _cn_num_to_float("壹佰贰拾万") == 1200000
    assert _cn_num_to_float("一百二十万") == 1200000
    assert _cn_num_to_float("一亿") == 100000000
    assert _cn_num_to_float("五千") == 5000
    assert _cn_num_to_float("一万") == 10000
    assert _cn_num_to_float("") is None
    assert _cn_num_to_float("abc") is None
    assert _cn_num_to_float("壹佰元") is None  # 元 不在映射表中


# ---------------------------------------------------------------- 合同规则

def test_contract_rules_full():
    res = extract_by_rules(1, CONTRACT_FIELDS, [CONTRACT_CHUNK_1, CONTRACT_CHUNK_2])
    assert res["source"] == "rule"
    assert res["data"]["contract_name"] == "产品购销合同"
    assert res["data"]["party_a"] == "华信科技有限公司"
    assert res["data"]["party_b"] == "远景供应链有限公司"
    assert res["data"]["sign_date"] == "2026-03-15"
    assert res["data"]["contract_amount"] == 1200000
    assert res["data"]["currency"] == "人民币"
    assert "预付款30%" in res["data"]["payment_method"]
    assert "30日内交货" in res["data"]["delivery_term"]
    assert "0.5%" in res["data"]["penalty_clause"]
    assert "人民法院" in res["data"]["dispute_resolution"]
    assert "一年" in res["data"]["valid_period"]
    assert res["field_status"]["contract_amount"] == "extracted"
    assert res["confidence"]["contract_amount"] == 0.9
    assert res["citations"]["contract_amount"][0]["chunk_id"] == 1
    # 11 个字段全部命中
    assert all(v == "extracted" for v in res["field_status"].values())
    assert len(res["data"]) == len(CONTRACT_FIELDS)


def test_contract_amount_variants():
    cases = [
        ("合同金额：人民币120万元整", 1200000),
        ("合同总价为人民币120万元", 1200000),
        ("合同总价为￥120万元", 1200000),
        ("合同金额：共计人民币1,200,000元", 1200000),
        ("合同金额约人民币1200万元", 12000000),
        ("合同金额：壹佰贰拾万元整", 1200000),
        ("合同金额：人民币壹佰贰拾万元整", 1200000),
    ]
    for text, expected in cases:
        res = extract_by_rules(1, CONTRACT_FIELDS, [_text_chunk(text, title="第一条")])
        assert res["data"]["contract_amount"] == expected, text


def test_contract_amount_from_table():
    chunk = _table_chunk("| 合同金额 | 1,200,000 元 |\n| 币种 | 人民币 |")
    res = extract_by_rules(1, CONTRACT_FIELDS, [chunk])
    assert res["data"]["contract_amount"] == 1200000
    assert res["data"]["currency"] == "人民币"


def test_sign_date_variants():
    res = extract_by_rules(
        1,
        CONTRACT_FIELDS,
        [_text_chunk("签署日期 2026-03-15", title="第一条")],
    )
    assert res["data"]["sign_date"] == "2026-03-15"


def test_sentence_field_confidence():
    res = extract_by_rules(
        1,
        CONTRACT_FIELDS,
        [_text_chunk("付款方式：预付款30%，验收合格后70%。", title="第二条")],
    )
    assert res["field_status"]["payment_method"] == "extracted"
    assert res["confidence"]["payment_method"] == 0.7


def test_missing_and_unknown_fields():
    res = extract_by_rules(1, CONTRACT_FIELDS, [_text_chunk("与合同无关的正文。")])
    assert res["data"]["party_a"] is None
    assert res["field_status"]["party_a"] == "missing"
    assert res["confidence"]["party_a"] == 0.0

    # 未知字段：无规则处理器 → missing
    fields = [{"key": "unknown_field", "label": "未知", "type": "string"}]
    res2 = extract_by_rules(1, fields, [_text_chunk("随便一段话。")])
    assert res2["field_status"]["unknown_field"] == "missing"
    assert res2["data"]["unknown_field"] is None


# ---------------------------------------------------------------- 财报规则

def test_financial_rules_full():
    chunk = _text_chunk(
        "报告期：2025年年度，公司主营业务：智能硬件研发与销售。\n"
        "营业收入85600万元，营业收入同比增长12.5%。\n"
        "净利润9800万元，净利润同比增长8.2%。\n"
        "毛利率32.1%，资产负债率45.6%，基本每股收益1.25元。",
        title="2025年年度报告",
    )
    res = extract_by_rules(1, FINANCIAL_FIELDS, [chunk])
    assert res["data"]["report_period"] == "2025年度"
    assert res["data"]["revenue"] == 85600
    assert res["data"]["revenue_yoy"] == 12.5
    assert res["data"]["net_profit"] == 9800
    assert res["data"]["profit_yoy"] == 8.2
    assert res["data"]["gross_margin"] == 32.1
    assert res["data"]["debt_ratio"] == 45.6
    assert res["data"]["eps"] == 1.25
    assert "智能硬件研发与销售" in res["data"]["main_business"]
    assert all(v == "extracted" for v in res["field_status"].values())
    assert len(res["data"]) == len(FINANCIAL_FIELDS)


def test_financial_table_and_unit_conversion():
    chunk = _table_chunk("| 营业收入 | 85600 万元 |\n| 毛利率 | 32.1% |")
    res = extract_by_rules(1, FINANCIAL_FIELDS, [chunk])
    assert res["data"]["revenue"] == 85600
    assert res["data"]["gross_margin"] == 32.1

    # 亿元 → 万元口径
    res2 = extract_by_rules(1, FINANCIAL_FIELDS, [_text_chunk("营业收入8.56亿元。")])
    assert res2["data"]["revenue"] == 85600


# ---------------------------------------------------------------- 归一化

def test_normalize_value_types():
    assert normalize_value({"type": "number"}, "￥1,200,000.00") == (1200000, True)
    assert normalize_value({"type": "number"}, "120万元") == (1200000, True)
    assert normalize_value({"type": "number"}, "12.5%") == (12.5, True)
    assert normalize_value({"type": "number"}, "(120)") == (-120, True)
    assert normalize_value({"type": "number"}, "abc") == (None, False)
    assert normalize_value({"type": "date"}, "2026年3月15日") == ("2026-03-15", True)
    assert normalize_value({"type": "date"}, "2026/3/5") == ("2026-03-05", True)
    assert normalize_value({"type": "date"}, "2026-13-40") == (None, False)
    assert normalize_value({"type": "list"}, "A、B，C;D") == (["A", "B", "C", "D"], True)
    assert normalize_value({"type": "list"}, [1, "x", ""]) == (["1", "x"], True)
    assert normalize_value({"type": "object"}, {"a": 1}) == ({"a": 1}, True)
    assert normalize_value({"type": "object"}, "abc") == ("abc", False)
    assert normalize_value({"type": "string"}, 123) == ("123", True)
    assert normalize_value(
        {"type": "string", "enum": ["人民币", "美元"]}, "美元"
    ) == ("美元", True)
    assert normalize_value(
        {"type": "string", "enum": ["人民币", "美元"]}, "USD"
    ) == (None, False)
    assert normalize_value({"type": "string"}, None) == (None, False)
    assert normalize_value({"type": "string"}, "  ") == (None, False)


# ---------------------------------------------------------------- JSON 解析 / 分批

def test_parse_json():
    assert _parse_json('{"a": 1}') == {"a": 1}
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json('前缀文本 {"a": 1} 后缀') == {"a": 1}
    assert _parse_json("不是 JSON") is None
    assert _parse_json("") is None
    assert _parse_json('{"a": 1') is None
    assert _parse_json("[1, 2]") is None  # 非对象


def test_batches():
    fields = [{"key": f"f{i}"} for i in range(10)]
    batches = _batches(fields)
    assert len(batches) == 2
    assert [f["key"] for f in batches[0]] == [f"f{i}" for i in range(8)]
    assert [f["key"] for f in batches[1]] == ["f8", "f9"]
    assert _batches(fields, 5) == [fields[0:5], fields[5:10]]
    assert _batches([], 8) == []