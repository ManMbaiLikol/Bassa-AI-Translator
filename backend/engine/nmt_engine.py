"""Moteur NMT — Traduction fr→Bassa.

Supporte deux modes selon ce qui a été entraîné par scripts/train_nmt.py :
  - "offline" : Transformer seq2seq from scratch + tokenizer SentencePiece
  - "marian"  : MarianMT fine-tuné (nécessite token HuggingFace à l'entraînement)

Le mode est détecté automatiquement à partir du fichier config.pkl.
"""
from __future__ import annotations

import logging
import math
import pickle
from pathlib import Path

from sqlalchemy.orm import Session

from backend.engine.base import TranslationEngine, TranslationResult

logger = logging.getLogger(__name__)

_NMT_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "backend" / "models_cache" / "nmt_fr_bassa"

try:
    import torch
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

try:
    import sentencepiece as spm
    _HAS_SP = True
except ImportError:
    _HAS_SP = False

_HAS_DEPS = _HAS_TORCH


class NMTEngine(TranslationEngine):
    """Moteur de traduction neuronal fr→Bassa."""

    def __init__(self, model_dir: str | Path | None = None):
        self._model_dir = Path(model_dir) if model_dir else _NMT_MODEL_DIR
        self._mode: str | None = None      # "offline" | "marian"
        self._model = None
        self._tokenizer = None             # Marian seulement
        self._sp = None                    # SentencePiece (offline seulement)
        self._cfg: dict = {}
        self._load_model()

    # ------------------------------------------------------------------
    # Chargement
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        if not _HAS_TORCH:
            logger.warning("torch manquant — moteur NMT désactivé.")
            return
        if not self._model_dir.exists():
            logger.info(
                "Moteur NMT : modèle non trouvé (%s). "
                "Lancez 'python scripts/train_nmt.py' pour l'entraîner.",
                self._model_dir,
            )
            return

        config_path = self._model_dir / "config.pkl"
        if not config_path.exists():
            logger.warning("config.pkl absent dans %s.", self._model_dir)
            return

        with open(config_path, "rb") as f:
            self._cfg = pickle.load(f)

        self._mode = self._cfg.get("mode", "offline")

        if self._mode == "marian":
            self._load_marian()
        else:
            self._load_offline()

    def _load_offline(self) -> None:
        if not _HAS_SP:
            logger.error("sentencepiece manquant — moteur NMT offline impossible.")
            return

        sp_path = self._model_dir / "spm.model"
        pt_path = self._model_dir / "model.pt"
        if not sp_path.exists() or not pt_path.exists():
            logger.warning("Fichiers NMT manquants dans %s.", self._model_dir)
            return

        try:
            self._sp = spm.SentencePieceProcessor()
            self._sp.load(str(sp_path))

            cfg = self._cfg
            self._model = _build_transformer(
                vocab_size=cfg["vocab_size"],
                d_model=cfg["d_model"],
                nhead=cfg["nhead"],
                num_layers=cfg["num_layers"],
                ffn_dim=cfg["ffn_dim"],
                pad_id=cfg["PAD_ID"],
            )
            state = torch.load(str(pt_path), map_location="cpu", weights_only=True)
            self._model.load_state_dict(state)
            self._model.eval()
            logger.info(
                "Moteur NMT offline prêt (vocab=%d, d=%d, layers=%d).",
                cfg["vocab_size"], cfg["d_model"], cfg["num_layers"],
            )
        except Exception as exc:
            logger.error("Erreur chargement NMT offline : %s", exc)
            self._model = None

    def _load_marian(self) -> None:
        try:
            from transformers import MarianMTModel, MarianTokenizer
            self._tokenizer = MarianTokenizer.from_pretrained(str(self._model_dir))
            self._model = MarianMTModel.from_pretrained(str(self._model_dir))
            self._model.eval()
            logger.info("Moteur NMT MarianMT prêt.")
        except Exception as exc:
            logger.error("Erreur chargement MarianMT : %s", exc)
            self._model = None

    # ------------------------------------------------------------------
    # Propriétés
    # ------------------------------------------------------------------

    @property
    def model_ready(self) -> bool:
        return self._model is not None

    # ------------------------------------------------------------------
    # Traduction
    # ------------------------------------------------------------------

    def translate(self, text: str, source_language: str) -> TranslationResult:
        if not text.strip():
            return TranslationResult(
                source_text=text, translated_text="",
                source_language=source_language, confidence=0.0, engine="nmt",
            )
        if not self.model_ready:
            return TranslationResult(
                source_text=text, translated_text="",
                source_language=source_language, confidence=0.0, engine="nmt",
                warnings=["Modèle NMT non disponible — lancez python scripts/train_nmt.py"],
            )
        if self._mode == "marian":
            return self._translate_marian(text, source_language)
        return self._translate_offline(text, source_language)

    def _translate_offline(self, text: str, source_language: str) -> TranslationResult:
        try:
            cfg     = self._cfg
            max_len = cfg.get("max_len", 80)
            PAD_ID  = cfg["PAD_ID"]
            BOS_ID  = cfg["BOS_ID"]
            EOS_ID  = cfg["EOS_ID"]

            def encode(t: str) -> list[int]:
                ids = [BOS_ID] + self._sp.encode(t, out_type=int) + [EOS_ID]
                if len(ids) > max_len:
                    ids = ids[:max_len - 1] + [EOS_ID]
                return ids + [PAD_ID] * (max_len - len(ids))

            src = torch.tensor([encode(text)])

            # Décodage greedy autorégressif.
            # Pré-allocation d'un tensor de taille max_len+1 pour éviter les
            # torch.cat() en boucle (O(n²) réallocations remplacées par O(1) écriture).
            # _model.eval() est déjà appelé au chargement — inutile de le répéter.
            output_ids = torch.full((1, max_len + 1), PAD_ID, dtype=torch.long)
            output_ids[0, 0] = BOS_ID
            step = 0
            with torch.no_grad():
                for step in range(max_len):
                    tgt_slice = output_ids[:, :step + 1]
                    logits = self._model(src, tgt_slice)   # (1, step+1, vocab)
                    next_id = int(logits[0, -1].argmax().item())
                    output_ids[0, step + 1] = next_id
                    if next_id == EOS_ID:
                        break

            pred_ids = output_ids[0, 1:step + 2].tolist()
            translated = self._sp.decode([i for i in pred_ids if i not in (EOS_ID, PAD_ID)])

            # Confiance estimée par la longueur relative de la traduction
            ratio = len(translated.split()) / max(1, len(text.split()))
            confidence = round(min(0.85, max(0.2, 1 - abs(1 - ratio) * 0.5)), 2)

            return TranslationResult(
                source_text=text,
                translated_text=translated,
                source_language=source_language,
                confidence=confidence,
                engine="nmt",
            )
        except Exception as exc:
            logger.error("Erreur NMT offline.translate : %s", exc)
            return TranslationResult(
                source_text=text, translated_text="",
                source_language=source_language, confidence=0.0, engine="nmt",
                warnings=[f"Erreur moteur NMT : {exc}"],
            )

    def _translate_marian(self, text: str, source_language: str) -> TranslationResult:
        try:
            inputs = self._tokenizer(
                [text], return_tensors="pt", truncation=True, max_length=128, padding=True,
            )
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs, num_beams=4, max_length=128, early_stopping=True,
                    output_scores=True, return_dict_in_generate=True,
                )
            translated = self._tokenizer.decode(outputs.sequences[0], skip_special_tokens=True)

            if hasattr(outputs, "sequences_scores") and outputs.sequences_scores is not None:
                confidence = round(math.exp(outputs.sequences_scores[0].item()), 2)
                confidence = max(0.0, min(1.0, confidence))
            else:
                confidence = 0.5

            return TranslationResult(
                source_text=text, translated_text=translated,
                source_language=source_language, confidence=confidence, engine="nmt",
            )
        except Exception as exc:
            logger.error("Erreur NMT marian.translate : %s", exc)
            return TranslationResult(
                source_text=text, translated_text="",
                source_language=source_language, confidence=0.0, engine="nmt",
                warnings=[str(exc)],
            )

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload(self, db: Session = None) -> None:
        """Recharge le modèle depuis le disque (après un nouvel entraînement)."""
        self._model = None
        self._tokenizer = None
        self._sp = None
        self._cfg = {}
        self._mode = None
        self._load_model()


# ---------------------------------------------------------------------------
# Construction de l'architecture Transformer (identique à train_nmt.py)
# ---------------------------------------------------------------------------

def _build_transformer(vocab_size: int, d_model: int, nhead: int, num_layers: int, ffn_dim: int, pad_id: int):
    """Reconstruit le modèle avec la même architecture qu'à l'entraînement."""
    import torch
    import torch.nn as nn

    class PositionalEncoding(nn.Module):
        def __init__(self):
            super().__init__()
            self.dropout = nn.Dropout(0.0)  # pas de dropout en inférence
            pe = torch.zeros(512, d_model)
            pos = torch.arange(0, 512).unsqueeze(1).float()
            div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
            pe[:, 0::2] = torch.sin(pos * div)
            pe[:, 1::2] = torch.cos(pos * div)
            self.register_buffer("pe", pe.unsqueeze(0))

        def forward(self, x):
            return self.dropout(x + self.pe[:, :x.size(1)])

    class Seq2SeqTransformer(nn.Module):
        def __init__(self):
            super().__init__()
            self.src_emb = nn.Embedding(vocab_size, d_model, padding_idx=pad_id)
            self.tgt_emb = nn.Embedding(vocab_size, d_model, padding_idx=pad_id)
            self.pos_enc = PositionalEncoding()
            enc = nn.TransformerEncoderLayer(d_model, nhead, ffn_dim, 0.1, batch_first=True)
            dec = nn.TransformerDecoderLayer(d_model, nhead, ffn_dim, 0.1, batch_first=True)
            self.encoder = nn.TransformerEncoder(enc, num_layers)
            self.decoder = nn.TransformerDecoder(dec, num_layers)
            self.fc_out  = nn.Linear(d_model, vocab_size)

        def forward(self, src: "torch.Tensor", tgt: "torch.Tensor") -> "torch.Tensor":
            src_pad = (src == pad_id)
            tgt_pad = (tgt == pad_id)
            L = tgt.size(1)
            causal = torch.triu(torch.ones(L, L, device=src.device), diagonal=1).bool()
            scale  = math.sqrt(d_model)
            src_e  = self.pos_enc(self.src_emb(src) * scale)
            tgt_e  = self.pos_enc(self.tgt_emb(tgt) * scale)
            mem    = self.encoder(src_e, src_key_padding_mask=src_pad)
            out    = self.decoder(tgt_e, mem, tgt_mask=causal, tgt_key_padding_mask=tgt_pad, memory_key_padding_mask=src_pad)
            return self.fc_out(out)

    return Seq2SeqTransformer()
