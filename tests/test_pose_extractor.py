from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.infrastructure.pose_extractor import (
    _POSE_EXTRACTION_INSTRUCTION,
    _is_pose_complete,
    _missing_pose_sections,
    _pose_sections_in_order,
)
from velvet_bot.presentation.telegram.routers.quality_operations_controllers import (
    velvet_ai_pose,
)


_COMPLETE_POSE = """
Vᴇʟᴠᴇᴛ Pᴏsᴇ
Количество персонажей:
Два человека, персонаж A ближе к камере.
Общая схема позы:
A стоит с переносом веса вправо, B сидит позади.
Голова и шея:
Голова A повёрнута влево, шея вытянута.
Корпус и таз:
Плечи A развёрнуты к камере, таз смещён вправо.
Руки и кисти:
Правая рука A согнута, кисть лежит на плече B.
Ноги и стопы:
Правая нога A несущая, левая согнута в колене.
Опоры и баланс:
Вес A приходится на правую стопу, B опирается на сиденье.
Контакты и перекрытия:
Кисть A касается плеча B, туловище A частично перекрывает B.
Ракурс и кадрирование:
Камера на уровне груди, левый нижний край обрезает стопу A.
Готовый pose prompt:
Два персонажа: A стоит ближе к камере с переносом веса на правую стопу и поворотом головы влево, B сидит позади, частично перекрытый туловищем A.
Negative prompts:
wrong pose, mirrored pose, swapped limbs, wrong hand placement, floating body, extra limbs, bad hands, bad feet.
""".strip()


class PoseExtractorTests(unittest.TestCase):
    def test_instruction_is_pose_only_and_anatomically_explicit(self) -> None:
        required = (
            "только геометрию человеческой позы",
            "не описывай интимную анатомию",
            "лево и право указывай относительно самого персонажа",
            "Опоры и баланс:",
            "Контакты и перекрытия:",
            "Готовый pose prompt:",
            "Negative prompts:",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, _POSE_EXTRACTION_INSTRUCTION)

    def test_complete_pose_contract_is_accepted(self) -> None:
        self.assertTrue(_is_pose_complete(_COMPLETE_POSE))
        self.assertTrue(_pose_sections_in_order(_COMPLETE_POSE))
        self.assertEqual((), _missing_pose_sections(_COMPLETE_POSE))

    def test_missing_or_reordered_sections_are_rejected(self) -> None:
        missing = _COMPLETE_POSE.replace("Опоры и баланс:", "Баланс:")
        reordered = _COMPLETE_POSE.replace(
            "Голова и шея:\nГолова A повёрнута влево, шея вытянута.\nКорпус и таз:",
            "Корпус и таз:\nПлечи A развёрнуты к камере.\nГолова и шея:",
        )

        self.assertFalse(_is_pose_complete(missing))
        self.assertIn("Опоры и баланс:", _missing_pose_sections(missing))
        self.assertFalse(_pose_sections_in_order(reordered))

    def test_completion_notice_reports_partial_comparison(self) -> None:
        notice = velvet_ai_pose._completion_notice(
            12,
            total_models=2,
            poses={"first": _COMPLETE_POSE},
            errors={"second": "model not found"},
        )

        self.assertIn("⚠️ Pose extractor #12 завершён частично", notice)
        self.assertIn("1 из 2", notice)
        self.assertIn("Ошибок: <b>1</b>", notice)

    def test_controller_delivers_text_and_registers_pose_job(self) -> None:
        source = Path(velvet_ai_pose.__file__).read_text(encoding="utf-8")
        self.assertIn('F.action == "poseextract_start"', source)
        self.assertIn('kind="pose_extraction"', source)
        self.assertIn("_send_pose_messages", source)
        self.assertNotIn("answer_document(", source)


if __name__ == "__main__":
    unittest.main()
