"""Central Checkmk policy for an agent/instance service."""
from cmk.rulesets.v1 import Help, Title
from cmk.rulesets.v1.form_specs import (
    DefaultValue, DictElement, Dictionary, Float, Integer, LevelDirection,
    List, SimpleLevels, SingleChoice, SingleChoiceElement, String,
)
from cmk.rulesets.v1.form_specs.validators import LengthInRange, MatchRegex, NumberInRange
from cmk.rulesets.v1.rule_specs import CheckParameters, HostAndItemCondition, Topic

from cmk_addons.plugins.forge_agents.lib.telemetry import METRICS

ALL_METRICS = dict(METRICS, execution_failure_percent='percent', verification_failure_percent='percent')


def parameter_form():
    levels = {}
    for key, unit in ALL_METRICS.items():
        template = Integer(custom_validate=(NumberInRange(min_value=0, max_value=10**15),)) if unit == 'count' else Float(
            custom_validate=(NumberInRange(min_value=0, max_value=100 if unit == 'percent' else 10**15),))
        levels[key] = DictElement(parameter_form=SimpleLevels(
            title=Title(key + ' (' + unit + ')'), form_spec_template=template,
            level_direction=LevelDirection.UPPER, prefill_fixed_levels=DefaultValue((0, 0))))
    return Dictionary(elements={
        'max_age_seconds': DictElement(required=True, parameter_form=Integer(
            title=Title('Maximum heartbeat age (seconds)'), prefill=DefaultValue(180),
            custom_validate=(NumberInRange(min_value=1, max_value=86400),))),
        'max_window_seconds': DictElement(required=True, parameter_form=Integer(
            title=Title('Maximum telemetry window (seconds)'), prefill=DefaultValue(3600),
            custom_validate=(NumberInRange(min_value=1, max_value=86400),))),
        'minimum_rate_samples': DictElement(required=True, parameter_form=Integer(
            title=Title('Minimum samples for failure percentages'), prefill=DefaultValue(5),
            custom_validate=(NumberInRange(min_value=1, max_value=10**15),))),
        'required_dependencies': DictElement(parameter_form=List(
            title=Title('Required dependency aliases'), custom_validate=(LengthInRange(max_value=32),),
            element_template=String(custom_validate=(MatchRegex(regex=r'\A[a-z0-9][a-z0-9_-]{0,63}\Z'),)))),
        'required_metrics': DictElement(parameter_form=List(
            title=Title('Required measurements'), custom_validate=(LengthInRange(max_value=len(ALL_METRICS)),),
            element_template=SingleChoice(elements=[SingleChoiceElement(name=key, title=Title(key)) for key in ALL_METRICS]))),
        'levels': DictElement(parameter_form=Dictionary(title=Title('Upper warning and critical thresholds'), elements=levels)),
    }, help_text=Help('Missing required measurements are UNKNOWN. A configured threshold also requires its measurement. Failure percentages need enough samples; idle is healthy when no rate is required. Counts cover the reported rolling window. No remediation is performed.'))


rule_spec_forge_agents = CheckParameters(
    name='forge_agents', title=Title('AI agent health and telemetry'), topic=Topic.APPLICATIONS,
    parameter_form=parameter_form, condition=HostAndItemCondition(item_title=Title('Agent/instance')),
)
