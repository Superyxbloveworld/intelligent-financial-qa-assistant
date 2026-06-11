from docqa.models import Word
from docqa.table_parser import group_lines, identify_table


def test_group_lines_uses_coordinates_not_extraction_order():
    words = [
        Word("100.00", 100, 20, 130, 30),
        Word("短期借款", 10, 20.5, 60, 30.5),
        Word("合计", 10, 50, 30, 60),
    ]
    lines = group_lines(words)
    assert len(lines) == 2
    assert lines[0].text == "短期借款 100.00"


def test_identify_financial_table_types():
    assert identify_table("被投资单位名称 本期增加") == "长期股权投资变动明细"
    assert identify_table("41 其他综合收益") == "其他综合收益"
    assert identify_table("非衍生金融负债 合同现金流量") == "金融负债合同现金流量"
