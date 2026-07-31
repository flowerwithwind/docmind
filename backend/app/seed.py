"""种子数据：内置 Schema、演示问题、样例注册信息。"""
from __future__ import annotations

from app.storage import db

CONTRACT_FIELDS = [
    {"key": "contract_name", "label": "合同名称", "type": "string", "required": True,
     "description": "合同标题或名称", "example": "产品购销合同", "prompt_hint": "", "enum": []},
    {"key": "party_a", "label": "甲方", "type": "string", "required": True,
     "description": "合同甲方全称", "example": "华信科技有限公司", "prompt_hint": "", "enum": []},
    {"key": "party_b", "label": "乙方", "type": "string", "required": True,
     "description": "合同乙方全称", "example": "远景供应链有限公司", "prompt_hint": "", "enum": []},
    {"key": "sign_date", "label": "签订日期", "type": "date", "required": True,
     "description": "合同签订日期", "example": "2026-03-15", "prompt_hint": "", "enum": []},
    {"key": "contract_amount", "label": "合同金额（元）", "type": "number", "required": True,
     "description": "合同总金额（人民币元），大写与小写不一致时以小写为准", "example": "1200000", "prompt_hint": "", "enum": []},
    {"key": "currency", "label": "币种", "type": "string", "required": False,
     "description": "合同约定币种", "example": "人民币", "prompt_hint": "", "enum": []},
    {"key": "payment_method", "label": "付款方式", "type": "string", "required": False,
     "description": "付款安排简述", "example": "预付款30%，验收后70%", "prompt_hint": "", "enum": []},
    {"key": "delivery_term", "label": "交付期限", "type": "string", "required": False,
     "description": "货物/服务交付期限", "example": "合同签订后30日内", "prompt_hint": "", "enum": []},
    {"key": "penalty_clause", "label": "违约金条款", "type": "string", "required": False,
     "description": "违约金比例或金额约定", "example": "逾期按合同金额0.5%/日支付违约金", "prompt_hint": "", "enum": []},
    {"key": "dispute_resolution", "label": "争议解决方式", "type": "string", "required": False,
     "description": "争议解决方式与管辖", "example": "提交甲方所在地人民法院诉讼解决", "prompt_hint": "", "enum": []},
    {"key": "valid_period", "label": "有效期", "type": "string", "required": False,
     "description": "合同有效期", "example": "自签订之日起一年", "prompt_hint": "", "enum": []},
]

FINANCIAL_FIELDS = [
    {"key": "report_period", "label": "报告期", "type": "string", "required": True,
     "description": "财务报告所属期间", "example": "2025年年度", "prompt_hint": "", "enum": []},
    {"key": "revenue", "label": "营业收入（万元）", "type": "number", "required": True,
     "description": "营业收入，单位万元", "example": "85600", "prompt_hint": "", "enum": []},
    {"key": "revenue_yoy", "label": "营业收入同比（%）", "type": "number", "required": False,
     "description": "营业收入同比增长率（百分数）", "example": "12.5", "prompt_hint": "", "enum": []},
    {"key": "net_profit", "label": "净利润（万元）", "type": "number", "required": True,
     "description": "归母净利润，单位万元", "example": "9800", "prompt_hint": "", "enum": []},
    {"key": "profit_yoy", "label": "净利润同比（%）", "type": "number", "required": False,
     "description": "净利润同比增长率（百分数）", "example": "8.2", "prompt_hint": "", "enum": []},
    {"key": "gross_margin", "label": "毛利率（%）", "type": "number", "required": False,
     "description": "销售毛利率（百分数）", "example": "32.1", "prompt_hint": "", "enum": []},
    {"key": "debt_ratio", "label": "资产负债率（%）", "type": "number", "required": False,
     "description": "资产负债率（百分数）", "example": "45.6", "prompt_hint": "", "enum": []},
    {"key": "eps", "label": "每股收益（元）", "type": "number", "required": False,
     "description": "基本每股收益", "example": "1.25", "prompt_hint": "", "enum": []},
    {"key": "main_business", "label": "主营业务", "type": "string", "required": False,
     "description": "主营业务描述", "example": "智能硬件研发与销售", "prompt_hint": "", "enum": []},
]

BUILTIN_SCHEMAS = [
    {"key": "contract", "name": "合同要素", "description": "合同关键条款结构化抽取", "fields": CONTRACT_FIELDS},
    {"key": "financial", "name": "财报指标", "description": "财务报告核心指标抽取", "fields": FINANCIAL_FIELDS},
]

DEMO_QUESTIONS = [
    "合同金额是多少？",
    "付款方式有哪些？",
    "违约金比例是多少？",
    "交付期限是什么时候？",
    "营业收入和净利润分别是多少？",
    "净利润同比增长多少？",
    "毛利率是多少？",
]

DEMO_SAMPLES = [
    {"kind": "contract", "name": "购销合同样例",
     "file": "demo-contract.pdf", "hint": "含金额 / 期限 / 违约条款 / 付款表格"},
    {"kind": "financial", "name": "财报摘要样例",
     "file": "demo-financial.pdf", "hint": "含营业收入 / 净利润 / 毛利率指标"},
    {"kind": "invoice", "name": "扫描发票样例",
     "file": "demo-invoice.png", "hint": "扫描件，需 OCR 或视觉模型"},
]


def ensure_seed_schemas() -> None:
    """启动时确保内置 Schema 存在（不覆盖用户修改）。"""
    for s in BUILTIN_SCHEMAS:
        existing = db.get_schema_by_key(s["key"])
        if existing is None:
            db.create_schema(s["key"], s["name"], s["description"], s["fields"], is_builtin=True)
