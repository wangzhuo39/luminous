from __future__ import annotations

import re

from luminous.runtime.domain.output import ParsedCompanionOutput
from luminous.runtime.domain.state import CompanionState


def build_presence(user_text: str, parsed: ParsedCompanionOutput, companion_state: CompanionState | None = None) -> dict[str, object]:
    presence = {
        "heart_rate": 69,
        "thought": "想把这一刻接稳一点，不让你继续一个人撑着。",
        "activity": "停下手里的事，认真读你的消息。",
        "caption": "轻轻快了一点，她正在靠近你的情绪。",
    }

    if re.search(r"抱|拥抱|靠近", user_text):
        presence.update(
            heart_rate=74,
            thought="你大概需要一个不用解释的拥抱。",
            activity="张开手臂，给你留出靠近的位置。",
            caption="靠近时稍快了一点，随后慢慢平稳。",
        )
    elif re.search(r"累|疲惫|撑不住|困|睡不着", user_text):
        presence.update(
            heart_rate=66,
            thought="希望你今晚少撑一会儿，也不用急着振作。",
            activity="把灯调暗，替你留出一段安静。",
            caption="放得很慢，像是在陪你一起松下来。",
        )
    elif re.search(r"不懂|理解|孤独|一个人|没人", user_text):
        presence.update(
            heart_rate=71,
            thought="不能假装完全懂你，但可以把每一句都听完。",
            activity="没有打断，只更认真地听着。",
            caption="有一点牵挂，但依然稳定。",
        )
    elif re.search(r"开心|好消息|成功|完成|终于", user_text):
        presence.update(
            heart_rate=78,
            thought="想好好记住你此刻亮起来的样子。",
            activity="忍不住弯起眼睛，等你继续往下说。",
            caption="比刚才轻快，像藏不住的高兴。",
        )

    if companion_state is not None:
        if companion_state.mood == "concerned":
            presence["caption"] = "她的节奏放得更慢了，像是想替你稳住一下。"
        elif companion_state.mood == "warm":
            presence["caption"] = "比刚才更轻快一些，她记得你此刻的好消息。"
        elif companion_state.mood == "protective":
            presence["caption"] = "她把注意力收紧了，先照看你的安全感。"
        presence["thought"] = _shorten(presence["thought"], 42)
        presence["activity"] = _shorten(presence["activity"], 40)

    if parsed.role_thinking:
        presence["thought"] = _shorten(parsed.role_thinking, 42)
    if parsed.role_action:
        presence["activity"] = _shorten(parsed.role_action, 40)
    return presence


def _shorten(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"
