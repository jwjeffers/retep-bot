from __future__ import annotations
"""Using an embedding model to vectorize question/reponse then score them using cosine similarity."""

import logging
from sentence_transformers import SentenceTransformer, CrossEncoder
import numpy as np
import math

logger = logging.getLogger(__name__)

class MessageScore:
    def __init__(self):
        self.model = SentenceTransformer(
            "nomic-ai/nomic-embed-text-v1.5",
            trust_remote_code=True,
            )
        self.ce_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu")

    def get_model(self):
        return self.model
    def get_ce_model(self):
        return self.ce_model
    def sigmoid(self, val):
        return 1 / (1 + math.exp(-val))

_scorer = None

def get_scorer():
    global _scorer
    if _scorer is None:
        _scorer = MessageScore()
    return _scorer

def score(input_text, output_text):
    score = get_scorer()
    # Get models
    ce_model = score.get_ce_model()
    model = score.get_model()
    # first get cross encoder score
    ce_score = float(ce_model.predict([(input_text, output_text)])[0])
    # sigmoid to put the score between 0-1
    ce_score = score.sigmoid(ce_score)
    logger.info(f"Cross encoder score: {ce_score}")
    # embed input and output messages
    input_formated = [f'search_query: {input_text}']
    output_formated = [f'search_query: {output_text}']
    # encode them
    embedding_in = model.encode(input_formated).reshape(-1)
    embedding_out = model.encode(output_formated).reshape(-1)
    # find cosine similarity
    cos_score = np.dot(embedding_in, embedding_out) / (np.linalg.norm(embedding_in) * np.linalg.norm(embedding_out))
    # normalize
    cos_score = (float(cos_score) + 1) / 2
    logger.info(f"Cosine similarity score: {cos_score}")
    # 80% encoder score 20% cosine similarity score
    finalScore = round((0.8*ce_score + 0.2*cos_score) *100, 2) 
    return finalScore
