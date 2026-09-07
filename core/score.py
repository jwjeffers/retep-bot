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
        self.ceModel = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu")

    def getModel(self):
        return self.model
    def getCEModel(self):
        return self.ceModel
    def sigmoid(self, val):
        return 1 / (1 + math.exp(-val))

global score

def score(input, output):
    score = MessageScore()
    # Get models
    ceModel = score.getCEModel()
    model = score.getModel()
    # first get cross encoder score
    ceScore = float(ceModel.predict([(input, output)])[0])
    ceScore = score.sigmoid(ceScore)
    logger.info(f"Cross encoder score: {ceScore}")
    # embed input and output messages
    inputFormated = [f'search_query: {input}']
    outputFormated = [f'search_query: {output}']
    # encode them
    embeddingIn = model.encode(inputFormated).reshape(-1)
    embeddingOut = model.encode(outputFormated).reshape(-1)
    # find cosine similarity
    cosScore = np.dot(embeddingIn, embeddingOut) / (np.linalg.norm(embeddingIn) * np.linalg.norm(embeddingOut))
    cosScore = (float(cosScore) + 1) / 2
    logger.info(f"Cosine similarity score: {cosScore}")
    # return scores added up
    finalScore = round((0.8*ceScore + 0.2*cosScore) *100, 2) 
    return finalScore
