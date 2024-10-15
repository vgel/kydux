import argparse
import os
import time
import json
import pathlib
import random
import sys
import typing

from repeng import ControlVector, DatasetEntry
from transformers import AutoTokenizer, AutoModelForCausalLM, PreTrainedTokenizerBase


def main():
    parser = argparse.ArgumentParser(description="kydux vector trainer")
    parser.add_argument(
        "--model", default="meta-llama/Meta-Llama-3-8B", help="huggingface model path"
    )
    parser.add_argument(
        "--span-size",
        type=int,
        default=20,
        help="number of tokens to use per example",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7777777,
        help="seed for data shuffling",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="batch size for vector training",
    )
    parser.add_argument(
        "--device",
        default="cuda:0",
        help="device to load model on",
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="directory of directories containing datafiles",
    )
    parser.add_argument(
        "--vector-dir",
        required=True,
        help="directory to write vectors to",
    )
    parser.add_argument(
        "vectors",
        nargs="*",
        help="names of data directories, which will be trained into vectors. default: all",
    )
    args = parser.parse_args()

    model_name: str = args.model
    span_size = int(args.span_size)
    seed = int(args.seed)
    batch_size = int(args.batch_size)
    device: str = args.device
    data_dir = pathlib.Path(args.data_dir)
    vector_dir = pathlib.Path(args.vector_dir)
    vectors = args.vectors
    if not vectors:
        vectors = [p.name for p in data_dir.iterdir() if p.is_dir()]

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token_id = 0
    model = AutoModelForCausalLM.from_pretrained(model_name)
    model = model.to(device)

    for v in vectors:
        dataset = read_and_chunk_dataset(data_dir / v, span_size, seed, tokenizer)
        print(f"{v}: {len(dataset)} examples", file=sys.stderr)
        vector = ControlVector.train(
            model, tokenizer, dataset, batch_size=batch_size, method="pca_center"
        )
        vector.export_gguf(str(vector_dir / f"{v}.gguf"))


def read_and_chunk_dataset(
    d: pathlib.Path, span_size: int, seed: int, tokenizer: PreTrainedTokenizerBase
) -> list[DatasetEntry]:
    positive_exs: list[str] = []
    negative_exs: list[str] = []

    for f in d.iterdir():
        if not f.is_file():
            continue
        elif "positive" not in f.name and "negative" not in f.name:
            print("unknown file type:", f, file=sys.stderr)
            continue

        with f.open() as hnd:
            contents = hnd.read()

        tokens = tokenizer.tokenize(contents)
        for i in range(len(tokens) - span_size):
            chunk = tokenizer.convert_tokens_to_string(tokens[i : i + span_size])
            if "positive" in f.name:
                positive_exs.append(chunk)
            else:
                negative_exs.append(chunk)

    random.seed(seed)
    random.shuffle(positive_exs)
    random.shuffle(negative_exs)

    return [
        DatasetEntry(
            positive=p,
            negative=n,
        )
        for p, n in zip(positive_exs, negative_exs)
    ]


if __name__ == "__main__":
    main()
