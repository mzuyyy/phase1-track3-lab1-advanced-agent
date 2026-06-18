import json

from src.reflexion_lab.utils import load_dataset, normalize_answer

def test_normalize_answer():
    assert normalize_answer("Oxford University!") == "oxford university"


def test_load_dataset_slice(tmp_path):
    dataset = [
        {
            "qid": str(index),
            "difficulty": "easy",
            "question": f"Question {index}",
            "gold_answer": f"Answer {index}",
            "context": [],
        }
        for index in range(3)
    ]
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(dataset), encoding="utf-8")

    examples = load_dataset(path, offset=1, limit=1)

    assert [example.qid for example in examples] == ["1"]
