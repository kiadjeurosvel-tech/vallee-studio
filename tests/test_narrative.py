import json

import pytest

from studio.narrative import validate, writer
from conftest import ROOT


def _state():
    return json.loads((ROOT / "memory" / "state.json").read_text())


def test_handwritten_episode_valid():
    ep = json.loads((ROOT / "story_queue" / "ep001.json").read_text())
    validate.normalize(ep)
    assert validate.check(ep)


@pytest.mark.parametrize("n", range(1, 13))
def test_templates_always_valid(n):
    st = _state()
    st["episode"] = n - 1
    ep = writer._from_templates(n, st, "A")
    assert ep["source"] == "gabarit"


def test_rejects_supernatural_and_unknown():
    ep = json.loads((ROOT / "story_queue" / "ep001.json").read_text())
    ep["lines"][2]["text"] = "Grumm, c'est de la magie, regarde ce dragon dans le ciel !"
    ep["lines"][3]["speaker"] = "GANDALF"
    validate.normalize(ep)
    with pytest.raises(validate.Invalid) as e:
        validate.check(ep)
    assert "interdit" in str(e.value) and "inconnu" in str(e.value)
