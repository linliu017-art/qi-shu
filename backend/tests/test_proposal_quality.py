from app.proposal import generation_template, rejects_unmentioned_as_excluded


def test_generation_template_replaces_ambiguous_scope_instructions_only():
    source = ('说明本期包含、明确不做和待确认内容。\n'
              '未在本期的公众入口、移动端、外部接口仅按需求基线记为后续或不纳入，不扩展为默认建设内容。')
    result = generation_template(source)
    assert '只有明确确认不做' in result
    assert '如未提及，是否纳入范围待确认' in result
    assert '仅按需求基线记为后续或不纳入' not in result
    assert 'DEMO-TPL-01' not in generation_template('模板标识 DEMO-TPL-01')


def test_direct_scope_contradiction_is_caught_without_blocking_uncertainty_or_confirmed_exclusions():
    assert rejects_unmentioned_as_excluded('未在本期的功能：移动端等需求清单未涉及，待核对原资料。')
    assert rejects_unmentioned_as_excluded('原资料未提及移动端，因此不纳入本期。')
    assert not rejects_unmentioned_as_excluded('资料未提及移动端，是否纳入本期待确认。')
    assert not rejects_unmentioned_as_excluded('未提及不代表不纳入本期。')
    assert not rejects_unmentioned_as_excluded('经客户确认，移动端本期不做。')
    assert not rejects_unmentioned_as_excluded('未涉及的库存计算口径需确认；客户已确认移动端本期不建设。')


def test_scope_check_rejects_treating_confirmed_functions_as_unconfirmed():
    assert rejects_unmentioned_as_excluded('以上待确认事项的结论未确定前，相关功能均不视为已确认范围。')
