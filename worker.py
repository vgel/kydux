import dataclasses
import json
import math
import os
import random
import time

import requests

N_CONTEXT = int(os.environ["N_CONTEXT"])
LOG = bool(os.getenv("LOG"))
MOCK_MODEL = bool(os.getenv("MOCK_MODEL"))
SECRET_URL = os.environ["SECRET_URL"]

MODEL_NAME = "meta-llama/Meta-Llama-3-8B"
CVEC = "vectors/kpunk_binglish.gguf"
MIN_CVEC, MAX_CVEC = -0.7, 1.5
# CVEC = "vectors/prophecies_analyses.gguf"
# MIN_CVEC, MAX_CVEC = -0.7, 0.7
SINUISOID_SCALE = 100
CONTROL_LAYERS = list(range(15, 28))
INITIAL_TEXT = "Bing is"


@dataclasses.dataclass
class Token:
    content: str
    raw_strength: float
    strength: float


class Generator:
    def __init__(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from repeng import ControlVector, ControlModel

        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.tokenizer.pad_token_id = 0
        model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.float16)
        model = model.to("cuda:0")
        self.model = ControlModel(model, CONTROL_LAYERS)
        self.vector = ControlVector.import_gguf(CVEC)

        self.tokens: list[str] = self.tokenizer.tokenize(INITIAL_TEXT)
        self.step = 0

        self.logfile = None
        if LOG:
            filename = f"kydux-{time.time()}.log"
            self.logfile = open(filename, "w")
            print(f"logging to {filename}")

    def next(self) -> Token:
        import torch

        raw_strength = math.sin(self.step / SINUISOID_SCALE)
        strength = (raw_strength + 1) / 2 * (MAX_CVEC - MIN_CVEC) + MIN_CVEC
        self.model.set_control(self.vector * strength)

        context = self.tokenizer.convert_tokens_to_string(self.tokens[-N_CONTEXT:])
        model_tokens = self.tokenizer(context, return_tensors="pt").to(
            self.model.device
        )
        logits = self.model.forward(**model_tokens).logits[0, -1, :]
        logits[self.tokenizer.eos_token_id] = -10000
        probs = torch.softmax(logits, dim=-1)
        next_token = torch.multinomial(probs, 1)
        self.tokens.append(self.tokenizer.decode(next_token))
        self.step += 1

        if self.logfile:
            self.logfile.write(f"{strength:+.5f}\t{self.tokens[-1]}\n")
            self.logfile.flush()

        return Token(
            content=self.tokens[-1],
            raw_strength=raw_strength,
            strength=strength,
        )


class MockGenerator:
    def __init__(self):
        self.step = 0

    def next(self) -> Token:
        time.sleep(0.1)
        raw_strength = math.sin(self.step / SINUISOID_SCALE)
        self.step += 1
        return Token(
            content=random.choice((" bing", " bong", ":-)")),
            raw_strength=raw_strength,
            strength=raw_strength,
        )


if __name__ == "__main__":
    if MOCK_MODEL:
        generator = MockGenerator()
    else:
        generator = Generator()

    while True:
        token = generator.next()
        message = json.dumps(dataclasses.asdict(token))
        try:
            requests.post(SECRET_URL, data=message).raise_for_status()
        except requests.RequestException as e:
            print(message)
            print(e)
