"""规则抽取器：无 LLM Key 时的演示降级路径（FR-06）。

基于关键词 / 正则 / 表格定位抽取，内置合同与财报字段规则；
置信度约定：关键词命中 0.6~0.9、正则精确 0.9+、表格定位 0.85。
"""

from __future__ import annotations

import re
from typing import Any

from app.models import Citation
from app.utils.text import normalize_value

_NUM = r"[-+]?\d[\d,，]*(?:\.\d+)?"
_SKIP_CELLS = {"单位", "金额", "数值", "指标", "项目", "名称", "备注", "说明"}

_CN_CHARS = "零〇一二三四五六七八九壹贰叁肆伍陆柒捌玖十拾百佰千仟万亿"

_CN_TABLE = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5, "陆": 6, "柒": 7, "捌": 8, "玖": 9,
}


def _cn_num_to_float(text: str) -> float | None:
    """将中文大小写数字（如 壹佰贰拾万元 / 一百二十万）转为数值。"""
    s = (text or "").strip()
    if not s:
        return None
    total = 0.0
    section = 0.0
    number = 0.0
    for ch in s:
        if ch in _CN_TABLE:
            number = float(_CN_TABLE[ch])
        elif ch in "十拾":
            section += (number or 1) * 10
            number = 0.0
        elif ch in "百佰":
            section += (number or 1) * 100
            number = 0.0
        elif ch in "千仟":
            section += (number or 1) * 1000
            number = 0.0
        elif ch in "万":
            total = (total + section + number) * 10000
            section = 0.0
            number = 0.0
        elif ch in "亿":
            total = (total + section + number) * 100000000
            section = 0.0
            number = 0.0
        else:
            return None
    return total + section + number


# 合同：需要"XX：名称"模式的字段
_PARTY_FIELDS = {
    "party_a": ("甲方", "合同甲方"),
    "party_b": ("乙方", "合同乙方"),
}

# 合同：句子类字段（关键词命中，取整句）
_SENTENCE_FIELDS: dict[str, tuple[list[str], float]] = {
    "payment_method": (["付款", "支付", "结算", "货款"], 0.7),
    "delivery_term": (["交货", "交付", "发货", "供货期", "供货时间"], 0.7),
    "penalty_clause": (["违约金", "违约责任"], 0.7),
    "dispute_resolution": (["争议", "纠纷", "仲裁", "诉讼", "法院"], 0.7),
    "valid_period": (["有效期", "合同期限", "本合同自", "履行期限"], 0.7),
}

# 财报：数值类字段（表格定位优先，正则兜底）
_FINANCIAL_FIELDS: dict[str, dict[str, Any]] = {
    "revenue": {"labels": ["营业收入", "主营业务收入", "营业总收入"], "policy": "wan"},
    "net_profit": {"labels": ["净利润", "归母净利润", "扣非净利润"], "policy": "wan"},
    "gross_margin": {"labels": ["毛利率", "销售毛利率"], "policy": "pct"},
    "debt_ratio": {"labels": ["资产负债率"], "policy": "pct"},
    "eps": {"labels": ["每股收益", "基本每股收益"], "policy": "yuan"},
}


class RuleExtractor:
    """按 Schema 字段定义执行规则抽取。"""

    def __init__(
        self, doc_id: int, fields: list[dict[str, Any]], chunks: list[dict[str, Any]]
    ) -> None:
        self.doc_id = doc_id
        self.fields = {f["key"]: f for f in fields}
        self.chunks = chunks
        self.text_chunks = [c for c in chunks if c.get("kind") != "table"]
        self.table_chunks = [c for c in chunks if c.get("kind") == "table"]
        self.results: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------ 基础工具

    def _hit(self, chunk: dict[str, Any] | None) -> list[dict[str, Any]]:
        if chunk is None:
            return []
        return [
            Citation(
                chunk_id=chunk["id"],
                page=chunk.get("page"),
                section=(chunk.get("section_path") or chunk.get("title") or ""),
                snippet=(chunk.get("content") or "").replace("\n", " ")[:120],
            ).model_dump()
        ]

    def _missing(self, key: str) -> None:
        self.results[key] = {
            "value": None, "confidence": 0.0, "status": "missing", "citations": [],
        }

    def _set(
        self, key: str, value: object, confidence: float,
        chunk: dict[str, Any] | None = None, status: str = "extracted",
    ) -> None:
        """写入单字段结果；非法值标记 invalid 并折半置信度。"""
        if value is None:
            self.results[key] = {
                "value": None,
                "confidence": round(confidence * 0.5, 3),
                "status": status,
                "citations": self._hit(chunk),
            }
            return
        normalized, ok = normalize_value(self.fields[key], value)
        if not ok:
            self.results[key] = {
                "value": None,
                "confidence": round(confidence * 0.5, 3),
                "status": "invalid",
                "citations": self._hit(chunk),
            }
            return
        if status == "extracted" and confidence < 0.5:
            status = "unsure"
        self.results[key] = {
            "value": normalized,
            "confidence": round(confidence, 3),
            "status": status,
            "citations": self._hit(chunk),
        }

    def _scan(self, pattern: re.Pattern[str]) -> tuple[re.Match[str] | None, dict[str, Any] | None]:
        """在全部块（正文优先）中扫描正则，返回 (首个匹配, 所在块)。"""
        for c in self.text_chunks + self.table_chunks:
            m = pattern.search(c.get("content") or "")
            if m:
                return m, c
        return None, None

    def _sentence(
        self, keywords: list[str], max_len: int = 90
    ) -> tuple[str | None, dict[str, Any] | None]:
        """返回包含任一关键词的整句（排除表头行）。"""
        pat = re.compile(
            r"[^。；;\n]*?(?:" + "|".join(re.escape(k) for k in keywords) + r")[^。；;\n]*"
        )
        for c in self.text_chunks + self.table_chunks:
            for line in (c.get("content") or "").splitlines():
                if line.strip().startswith("|"):
                    continue
                m = pat.search(line)
                if m:
                    s = m.group(0).strip()
                    if s and len(s) <= max_len:
                        return s, c
        return None, None

    def _table_value(
        self, labels: list[str], max_len: int = 40
    ) -> tuple[str | None, dict[str, Any] | None]:
        """在表格块中按标签行定位取值，返回 (值单元格, 块)。"""
        for c in self.table_chunks:
            for line in (c.get("content") or "").splitlines():
                line = line.strip()
                if not line.startswith("|"):
                    continue
                cells = [x.strip() for x in line.strip("|").split("|")]
                for i, cell in enumerate(cells):
                    if not any(lbl in cell for lbl in labels):
                        continue
                    for j, v in enumerate(cells):
                        if j == i or not v or v in _SKIP_CELLS:
                            continue
                        if len(v) > max_len:
                            continue
                        return v, c
        return None, None

    def _set_financial(
        self, key: str, raw: object, chunk: dict[str, Any] | None, policy: str
    ) -> None:
        """财报数值：按单位策略换算（wan=万元口径 / pct=百分比 / yuan=元）。"""
        s = str(raw).strip()
        m = re.match(rf"^(?P<num>{_NUM})\s*(?P<unit>亿元|万元|元|[%％])?$", s)
        if not m:
            self._set(key, None, 0.6, chunk, status="invalid")
            return
        num = float(m.group("num").replace(",", "").replace("，", ""))
        unit = m.group("unit")
        if policy == "pct":
            pass
        elif policy == "yuan":
            pass
        elif unit == "亿元":
            num *= 10000
        elif unit == "元":
            num /= 10000
        # 无单位 / 万元：保持（表格表头已声明口径）
        self._set(key, num, 0.9, chunk)

    # ------------------------------------------------------------ 合同字段

    def _rule_contract_name(self) -> None:
        for c in self.text_chunks:
            title = (c.get("title") or "").strip()
            if title and "合同" in title:
                self._set("contract_name", title, 0.9, c)
                return
        m, c = self._scan(re.compile(r"(?:合同名称|合同标题)\s*[：:]\s*([^\s，。；、,;]{2,50})"))
        if m:
            self._set("contract_name", m.group(1), 0.9, c)
            return
        for c in self.text_chunks[:3]:
            first = (c.get("content") or "").strip().splitlines()[0].strip()
            if first and len(first) <= 30 and "合同" in first:
                self._set("contract_name", first, 0.7, c)
                return
        self._missing("contract_name")

    def _rule_party_a(self) -> None:
        self._rule_party("party_a")

    def _rule_party_b(self) -> None:
        self._rule_party("party_b")

    def _rule_party(self, key: str) -> None:
        label, _ = _PARTY_FIELDS[key]
        m, c = self._scan(
            re.compile(rf"{label}\s*[：:]\s*([^\s，。；、,;（）()]{{2,50}})")
        )
        if m:
            self._set(key, m.group(1), 0.9, c)
            return
        self._missing(key)

    def _rule_sign_date(self) -> None:
        patterns = [
            re.compile(
                r"(?:签订|签署|签字|签约)\s*(?:日期|时间)?\s*[：:]?\s*"
                r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})"
            ),
            re.compile(r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)"),
            re.compile(r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})"),
        ]
        for p in patterns:
            m, c = self._scan(p)
            if m:
                self._set("sign_date", m.group(1), 0.9, c)
                return
        self._missing("sign_date")

    def _rule_contract_amount(self) -> None:
        hit = self._table_value(
            ["合同金额", "合同总金额", "总金额", "合同总价", "价款", "总价", "金额"]
        )
        if hit[0]:
            self._set_amount(hit[0], hit[1])
            return
        prefix_skip = r"(?:为|是|约|共计)?\s*(?:人民币|￥|¥)?\s*"
        patterns = [
            re.compile(
                r"(?:合同金额|合同总金额|总金额|合同总价|价款|总价)\s*[：:]?\s*"
                + prefix_skip
                + rf"((?:{_NUM})\s*(?:万元|亿元|元|人民币)?)"
            ),
            re.compile(
                r"(?:合同金额|合同总金额|总金额|合同总价|价款|总价)\s*[：:]?\s*"
                + prefix_skip
                + rf"([{_CN_CHARS}]+元?)"
            ),
        ]
        for p in patterns:
            m, c = self._scan(p)
            if m:
                self._set_amount(m.group(1), c)
                return
        self._missing("contract_amount")

    def _set_amount(self, raw: object, chunk: dict[str, Any] | None) -> None:
        s = str(raw).strip()
        if re.search(r"[零〇一二三四五六七八九壹贰叁肆伍陆柒捌玖]", s):
            v = _cn_num_to_float(s.rstrip("元"))
            self._set("contract_amount", v, 0.9, chunk)
            return
        m = re.match(rf"^(?P<num>{_NUM})\s*(?P<unit>万元|亿元|元|人民币)?$", s)
        if not m:
            self._set("contract_amount", None, 0.6, chunk, status="invalid")
            return
        num = float(m.group("num").replace(",", "").replace("，", ""))
        unit = m.group("unit")
        if unit == "万元":
            num *= 10000
        elif unit == "亿元":
            num *= 100000000
        self._set("contract_amount", num, 0.9, chunk)

    def _rule_currency(self) -> None:
        m, c = self._scan(re.compile(r"(人民币|美元|欧元|日元|港币|英镑)"))
        if m:
            self._set("currency", m.group(1), 0.7, c)
            return
        self._missing("currency")

    def _rule_sentence_field(self, key: str) -> None:
        keywords, conf = _SENTENCE_FIELDS[key]
        s, c = self._sentence(keywords)
        if s:
            self._set(key, s, conf, c)
            return
        self._missing(key)

    def __getattr__(self, name: str) -> Any:
        # 句子类字段统一处理：_rule_payment_method / _rule_delivery_term 等
        if name.startswith("_rule_") and name[len("_rule_"):] in _SENTENCE_FIELDS:
            key = name[len("_rule_"):]
            return lambda: self._rule_sentence_field(key)
        if name.startswith("_rule_") and name[len("_rule_"):] in _FINANCIAL_FIELDS:
            key = name[len("_rule_"):]
            return lambda: self._rule_financial(key)
        raise AttributeError(name)

    # ------------------------------------------------------------ 财报字段

    def _rule_report_period(self) -> None:
        patterns = [
            re.compile(r"(20\d{2})\s*年\s*(?:年)?\s*(?:度|年报|全年|报告)"),
            re.compile(r"报告期\s*[：:]?\s*(20\d{2})\s*年(?:度|年报|全年|报告)?[^，。；\n]{0,10}"),
        ]
        for p in patterns:
            m, c = self._scan(p)
            if m:
                self._set("report_period", f"{m.group(1)}年度", 0.9, c)
                return
        self._missing("report_period")

    def _rule_financial(self, key: str) -> None:
        cfg = _FINANCIAL_FIELDS[key]
        hit = self._table_value(cfg["labels"])
        if hit[0]:
            self._set_financial(key, hit[0], hit[1], cfg["policy"])
            return
        pat = re.compile(
            r"(?:"
            + "|".join(re.escape(l) for l in cfg["labels"])
            + r")\s*[：:]?\s*"
            + rf"(?P<num>{_NUM})\s*(?P<unit>亿元|万元|元|[%％])?"
        )
        m, c = self._scan(pat)
        if m:
            raw = f"{m.group('num')}{m.group('unit') or ''}"
            self._set_financial(key, raw, c, cfg["policy"])
            return
        self._missing(key)

    def _rule_revenue_yoy(self) -> None:
        self._rule_yoy("revenue_yoy", ["营业收入", "营收", "主营业务收入"])

    def _rule_profit_yoy(self) -> None:
        self._rule_yoy("profit_yoy", ["净利润", "归母净利润", "扣非净利润"])

    def _rule_yoy(self, key: str, metrics: list[str]) -> None:
        pat = re.compile(
            r"(?:"
            + "|".join(re.escape(m) for m in metrics)
            + r")[^。；;\n]{0,20}同比[^。；;\n]{0,10}?"
            + rf"({_NUM})\s*[%％]"
        )
        m, c = self._scan(pat)
        if m:
            self._set(key, m.group(1), 0.85, c)
            return
        self._missing(key)

    def _rule_main_business(self) -> None:
        s, c = self._sentence(["主营业务", "经营范围", "主要业务"], max_len=60)
        if s:
            self._set("main_business", s, 0.6, c)
            return
        self._missing("main_business")


def extract_by_rules(
    doc_id: int, fields: list[dict[str, Any]], chunks: list[dict[str, Any]]
) -> dict[str, Any]:
    """对全部字段执行规则抽取，返回合并结果 dict。"""
    ex = RuleExtractor(doc_id, fields, chunks)
    for key in [f["key"] for f in fields]:
        handler = getattr(ex, f"_rule_{key}", None)
        if handler is not None:
            handler()
        else:
            ex._missing(key)
    data: dict[str, Any] = {}
    confidence: dict[str, float] = {}
    field_status: dict[str, str] = {}
    citations: dict[str, list[dict[str, Any]]] = {}
    for key, r in ex.results.items():
        data[key] = r["value"]
        confidence[key] = r["confidence"]
        field_status[key] = r["status"]
        citations[key] = r["citations"]
    return {
        "data": data,
        "confidence": confidence,
        "field_status": field_status,
        "citations": citations,
        "source": "rule",
    }