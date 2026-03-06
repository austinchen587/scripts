# vectorizer.py
from transformers import AutoTokenizer, AutoModel
import torch

class TextVectorizer:
    def __init__(self, model_path=None):
        from config import TEXT2VEC_MODEL_PATH
        path = model_path or TEXT2VEC_MODEL_PATH
        self.tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(path, trust_remote_code=True)
        self.model.eval()
        if torch.cuda.is_available():
            self.model = self.model.cuda()

    def encode(self, text: str):
        with torch.no_grad():
            inputs = self.tokenizer([text], padding=True, truncation=True, return_tensors="pt", max_length=512)
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            embedding = self.model(**inputs).pooler_output[0]
            if torch.cuda.is_available():
                embedding = embedding.cpu()
            return embedding.numpy().tolist()
