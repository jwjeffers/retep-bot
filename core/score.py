from __future__ import annotations
"""Score how well Retep's response answers a question using a conversational model and cosine similarity."""

import logging
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer
import numpy as np
import math
import threading
import torch

logger = logging.getLogger(__name__)

# Per-token PMI is mapped to 0-1 with sigmoid(PMI_SCALE * (pmi - PMI_CENTER)).
# Good replies land around 2+, off-topic replies near 0, generic ones below 0.
PMI_CENTER = 1.0
PMI_SCALE = 2.0
# Keep inputs within DialoGPT's 1024 position limit
MAX_CONTEXT_TOKENS = 512
MAX_REPLY_TOKENS = 256

class MessageScore:
    def __init__(self):
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
        self.dialog_tokenizer = AutoTokenizer.from_pretrained("microsoft/DialoGPT-small")
        # The checkpoint is float16, which is very slow on CPU. bfloat16 uses the same half
        # memory of float16 but is fast on most CPUs; switch to torch.float32 if scoring is slow
        self.dialog_model = AutoModelForCausalLM.from_pretrained("microsoft/DialoGPT-small", dtype=torch.bfloat16)
        self.dialog_model.eval()

    def get_model(self):
        return self.model
    def get_dialog_model(self):
        return self.dialog_model
    def get_dialog_tokenizer(self):
        return self.dialog_tokenizer
    def sigmoid(self, val):
        return 1 / (1 + math.exp(-val))

_scorer = None
# score() runs in worker threads, so guard against two threads loading the models at once
_scorer_lock = threading.Lock()
# The Hugging Face tokenizers aren't safe to share across threads, and each model call
# already uses every CPU core, so run one score at a time
_inference_lock = threading.Lock()

def get_scorer():
    global _scorer
    with _scorer_lock:
        if _scorer is None:
            _scorer = MessageScore()
    return _scorer

def _words(text):
    return [w.lower().strip(".,!?\"'") for w in text.split()]

def strip_echo(input_text, output_text):
    """Remove words from the output that were copied from a one-word input."""
    if len(input_text.split()) >= 2:
        return output_text
    seed = set(_words(input_text))
    return " ".join(w for w, clean in zip(output_text.split(), _words(output_text)) if clean not in seed)

def reply_logprob(scorer, context, reply):
    """Total log-probability DialoGPT assigns to reply following context, and the reply's token count."""
    tokenizer = scorer.get_dialog_tokenizer()
    model = scorer.get_dialog_model()
    eos = tokenizer.eos_token
    context_ids = tokenizer.encode(context + eos)[-MAX_CONTEXT_TOKENS:]
    reply_ids = tokenizer.encode(reply + eos)[:MAX_REPLY_TOKENS]
    ids = torch.tensor([context_ids + reply_ids])
    with torch.no_grad():
        # softmax in float32 so small probabilities aren't lost to bfloat16 rounding
        logits = model(ids).logits[0].float()
    # logits at position i predict token i + 1
    logprobs = torch.log_softmax(logits[:-1], dim=-1)
    targets = ids[0, 1:]
    token_logprobs = logprobs[torch.arange(len(targets)), targets]
    return float(token_logprobs[len(context_ids) - 1:].sum()), len(reply_ids)

def relevance(scorer, input_text, output_text):
    """
    Pointwise mutual information: how much more likely the reply is given the question
    than on its own. Generic replies ("lol") score low because they fit anything.
    """
    conditional, n_tokens = reply_logprob(scorer, input_text, output_text)
    unconditional, _ = reply_logprob(scorer, "", output_text)
    pmi = (conditional - unconditional) / n_tokens
    logger.info(f"Per-token PMI: {pmi}")
    return scorer.sigmoid(PMI_SCALE * (pmi - PMI_CENTER))

def score(input_text, output_text):
    scorer = get_scorer()
    with _inference_lock:
        return _score(scorer, input_text, output_text)

def _score(scorer, input_text, output_text):
    model = scorer.get_model()
    # one-word inputs (usually a name) get inflated scores when Retep repeats them back
    output_text = strip_echo(input_text, output_text)
    if not output_text.strip():
        logger.info("Response only repeated the input")
        return 0.0
    # first get conversational relevance score (already between 0-1)
    rel_score = relevance(scorer, input_text, output_text)
    logger.info(f"Relevance score: {rel_score}")
    # embed input and output messages (MiniLM takes plain text, no task prefix)
    embedding_in = model.encode([input_text]).reshape(-1)
    embedding_out = model.encode([output_text]).reshape(-1)
    # find cosine similarity
    cos_score = np.dot(embedding_in, embedding_out) / (np.linalg.norm(embedding_in) * np.linalg.norm(embedding_out))
    # normalize
    cos_score = (float(cos_score) + 1) / 2
    logger.info(f"Cosine similarity score: {cos_score}")
    # 80% relevance score 20% cosine similarity score
    final_score = round((0.8*rel_score + 0.2*cos_score) *100, 2)
    return final_score
