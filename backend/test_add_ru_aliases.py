from add_ru_aliases import aliases_for_translation


def test_comma_separated_translation_becomes_individual_aliases():
    assert aliases_for_translation("Мирный, спокойный, тихий") == {
        "мирный",
        "спокойный",
        "тихий",
    }