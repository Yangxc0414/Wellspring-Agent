"""Local frozen causal-LM adapter; no network, no training."""

import os
from pathlib import Path
from typing import List, Sequence

from ..ports import ModelPort


class LocalModelError(RuntimeError):
    pass


class LocalHFModel(ModelPort):
    def __init__(self, model_path: Path, max_new_tokens: int = 180):
        os.environ.setdefault("USE_TF", "0")
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise LocalModelError("torch/transformers are required for the local model") from exc
        path = Path(model_path).expanduser()
        if not path.is_dir():
            raise LocalModelError("local model directory not found: " + str(path))
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)
            self._model = AutoModelForCausalLM.from_pretrained(
                str(path), local_files_only=True, torch_dtype=torch.float32
            )
        except OSError as exc:
            raise LocalModelError("could not load local model: " + str(path)) from exc
        self._torch = torch
        self._model.eval()
        self._max_new_tokens = max_new_tokens
        self.model_id = "local-qwen2.5-0.5b-instruct"

    def complete(self, messages: Sequence[dict], json_mode: bool = True) -> str:
        prompt = self._tokenizer.apply_chat_template(
            list(messages), tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(prompt, return_tensors="pt")
        with self._torch.no_grad():
            output = self._model.generate(
                **inputs,
                max_new_tokens=self._max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                top_k=None,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        generated: List[int] = output[0][inputs["input_ids"].shape[1]:].tolist()
        return self._tokenizer.decode(generated, skip_special_tokens=True)
