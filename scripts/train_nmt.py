#!/usr/bin/env python3
"""Fine-tuning NMT fr→Bassa — fonctionne 100% hors-ligne.

Deux modes :
  1. Hors-ligne (défaut) : Transformer seq2seq entraîné depuis zéro
     sur le corpus de l'application. Aucun téléchargement requis.

  2. MarianMT (optionnel) : Fine-tuning du modèle Helsinki-NLP
     pré-entraîné si un token HuggingFace est fourni.
     python scripts/train_nmt.py --hf-token hf_xxxxx

Usage :
    python scripts/train_nmt.py                          # mode hors-ligne
    python scripts/train_nmt.py --epochs 30 --batch-size 64
    python scripts/train_nmt.py --hf-token hf_xxxxx     # mode MarianMT

Modèle sauvegardé dans backend/models_cache/nmt_fr_bassa/.
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import pickle
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "mysql+pymysql://root:@localhost/bassa_translator")

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = ROOT / "backend" / "models_cache" / "nmt_fr_bassa"
DEFAULT_BASE_MODEL = "Helsinki-NLP/opus-mt-fr-kg"


def _is_server_running(port: int = 8000) -> bool:
    """Vérifie si le serveur FastAPI tourne sur localhost:port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0

# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

def load_corpus() -> list[tuple[str, str]]:
    from backend.database import SessionLocal
    from backend.models.corpus import CorpusPair

    db = SessionLocal()
    try:
        pairs = (
            db.query(CorpusPair)
            .filter(CorpusPair.is_verified == True, CorpusPair.source_language == "fr")  # noqa: E712
            .all()
        )
        result = [
            (p.source_text.strip(), p.bassa_text.strip())
            for p in pairs
            if p.source_text.strip() and p.bassa_text.strip()
        ]
        logger.info("%d paires fr→Bassa chargées.", len(result))
        return result
    finally:
        db.close()


# ===========================================================================
# MODE 1 — Transformer from scratch (100% hors-ligne)
# ===========================================================================

def train_offline(args: argparse.Namespace) -> None:
    """Entraîne un Transformer seq2seq fr→Bassa sans téléchargement."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, Dataset
    from torch.optim import AdamW
    from transformers import get_linear_schedule_with_warmup
    import sentencepiece as spm
    import io

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device : %s", device)

    # ---- Corpus ----
    data = load_corpus()
    random.seed(42)
    random.shuffle(data)
    split = max(20, int(len(data) * 0.9))
    train_data, val_data = data[:split], data[split:]
    logger.info("Train : %d | Validation : %d", len(train_data), len(val_data))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---- Entraîner le tokenizer SentencePiece ----
    sp_model_path = output_dir / "spm.model"
    if not sp_model_path.exists():
        logger.info("Entraînement du tokenizer SentencePiece (vocab=%d)...", args.vocab_size)
        corpus_file = output_dir / "_corpus_tmp.txt"
        with corpus_file.open("w", encoding="utf-8") as f:
            for fr, ba in data:
                f.write(fr + "\n")
                f.write(ba + "\n")
        spm.SentencePieceTrainer.train(
            input=str(corpus_file),
            model_prefix=str(output_dir / "spm"),
            vocab_size=args.vocab_size,
            character_coverage=1.0,          # couvre tous les caractères Bassa
            model_type="bpe",
            pad_id=0, unk_id=1, bos_id=2, eos_id=3,
            pad_piece="<pad>", unk_piece="<unk>",
            bos_piece="<s>", eos_piece="</s>",
        )
        corpus_file.unlink()
        logger.info("Tokenizer sauvegardé : %s", sp_model_path)
    else:
        logger.info("Tokenizer existant chargé : %s", sp_model_path)

    sp = spm.SentencePieceProcessor()
    sp.load(str(sp_model_path))
    vocab_size = sp.get_piece_size()
    PAD_ID = sp.pad_id()
    BOS_ID = sp.bos_id()
    EOS_ID = sp.eos_id()
    logger.info("Vocabulaire SentencePiece : %d tokens", vocab_size)

    # ---- Dataset ----
    def encode(text: str, max_len: int) -> list[int]:
        ids = [BOS_ID] + sp.encode(text, out_type=int) + [EOS_ID]
        if len(ids) > max_len:
            ids = ids[:max_len - 1] + [EOS_ID]
        return ids + [PAD_ID] * (max_len - len(ids))

    class TranslationDataset(Dataset):
        def __init__(self, pairs: list[tuple[str, str]]):
            import torch
            self.src = torch.tensor([encode(fr, args.max_len) for fr, _ in pairs], dtype=torch.long)
            self.tgt = torch.tensor([encode(ba, args.max_len) for _, ba in pairs], dtype=torch.long)

        def __len__(self) -> int:
            return len(self.src)

        def __getitem__(self, idx):
            return self.src[idx], self.tgt[idx]

    logger.info("Tokenisation du corpus...")
    train_ds = TranslationDataset(train_data)
    val_ds   = TranslationDataset(val_data)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size)

    # ---- Modèle Transformer ----
    class PositionalEncoding(nn.Module):
        def __init__(self, d_model: int, max_len: int = 512, dropout: float = 0.1):
            super().__init__()
            self.dropout = nn.Dropout(dropout)
            pe = torch.zeros(max_len, d_model)
            pos = torch.arange(0, max_len).unsqueeze(1).float()
            div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
            pe[:, 0::2] = torch.sin(pos * div)
            pe[:, 1::2] = torch.cos(pos * div)
            self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, d_model)

        def forward(self, x):
            return self.dropout(x + self.pe[:, :x.size(1)])

    class Seq2SeqTransformer(nn.Module):
        def __init__(self, vocab_size: int, d_model: int, nhead: int, num_layers: int, ffn_dim: int, dropout: float = 0.1):
            super().__init__()
            self.src_emb = nn.Embedding(vocab_size, d_model, padding_idx=PAD_ID)
            self.tgt_emb = nn.Embedding(vocab_size, d_model, padding_idx=PAD_ID)
            self.pos_enc = PositionalEncoding(d_model, dropout=dropout)
            encoder_layer = nn.TransformerEncoderLayer(d_model, nhead, ffn_dim, dropout, batch_first=True)
            decoder_layer = nn.TransformerDecoderLayer(d_model, nhead, ffn_dim, dropout, batch_first=True)
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers)
            self.decoder = nn.TransformerDecoder(decoder_layer, num_layers)
            self.fc_out  = nn.Linear(d_model, vocab_size)
            self._init_weights()

        def _init_weights(self):
            for p in self.parameters():
                if p.dim() > 1:
                    nn.init.xavier_uniform_(p)

        def forward(self, src, tgt):
            src_pad_mask = (src == PAD_ID)
            tgt_pad_mask = (tgt == PAD_ID)
            tgt_len = tgt.size(1)
            causal_mask = torch.triu(torch.ones(tgt_len, tgt_len, device=src.device), diagonal=1).bool()

            src_emb = self.pos_enc(self.src_emb(src) * math.sqrt(self.src_emb.embedding_dim))
            tgt_emb = self.pos_enc(self.tgt_emb(tgt) * math.sqrt(self.tgt_emb.embedding_dim))

            mem = self.encoder(src_emb, src_key_padding_mask=src_pad_mask)
            out = self.decoder(tgt_emb, mem, tgt_mask=causal_mask, tgt_key_padding_mask=tgt_pad_mask, memory_key_padding_mask=src_pad_mask)
            return self.fc_out(out)

        @torch.no_grad()
        def generate(self, src: torch.Tensor, max_len: int = 64) -> list[int]:
            self.eval()
            src_pad = (src == PAD_ID)
            src_emb = self.pos_enc(self.src_emb(src) * math.sqrt(self.src_emb.embedding_dim))
            mem = self.encoder(src_emb, src_key_padding_mask=src_pad)

            tgt = torch.tensor([[BOS_ID]], device=src.device)
            for _ in range(max_len):
                tgt_emb = self.pos_enc(self.tgt_emb(tgt) * math.sqrt(self.tgt_emb.embedding_dim))
                tgt_len = tgt.size(1)
                causal = torch.triu(torch.ones(tgt_len, tgt_len, device=src.device), diagonal=1).bool()
                out = self.decoder(tgt_emb, mem, tgt_mask=causal)
                next_id = self.fc_out(out[:, -1]).argmax(-1, keepdim=True)
                tgt = torch.cat([tgt, next_id], dim=1)
                if next_id.item() == EOS_ID:
                    break
            return tgt[0, 1:].tolist()

    model = Seq2SeqTransformer(
        vocab_size=vocab_size,
        d_model=args.d_model,
        nhead=args.nhead,
        num_layers=args.num_layers,
        ffn_dim=args.ffn_dim,
        dropout=0.1,
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters())
    logger.info("Modèle : %dM paramètres", n_params // 1_000_000)

    # ---- Optimiseur ----
    criterion = nn.CrossEntropyLoss(ignore_index=PAD_ID, label_smoothing=0.1)
    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, max(1, total_steps // 10), total_steps)

    best_val_loss = float("inf")

    logger.info("=" * 60)
    logger.info("Démarrage entraînement — %d epochs, batch=%d, d_model=%d", args.epochs, args.batch_size, args.d_model)
    logger.info("Durée estimée CPU : %.0f–%.0f minutes", (total_steps * 0.3) / 60, (total_steps * 0.8) / 60)
    logger.info("=" * 60)

    for epoch in range(1, args.epochs + 1):
        # ---- Train ----
        model.train()
        train_loss = 0.0
        for step, (src, tgt) in enumerate(train_loader, 1):
            src, tgt = src.to(device), tgt.to(device)
            tgt_in  = tgt[:, :-1]
            tgt_out = tgt[:, 1:].contiguous()

            logits = model(src, tgt_in)                          # (B, T-1, V)
            loss = criterion(logits.view(-1, vocab_size), tgt_out.view(-1))

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

            train_loss += loss.item()
            if step % 50 == 0 or step == len(train_loader):
                logger.info("Epoch %d/%d | Step %d/%d | Loss : %.4f", epoch, args.epochs, step, len(train_loader), train_loss / step)

        avg_train = train_loss / len(train_loader)

        # ---- Validation ----
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for src, tgt in val_loader:
                src, tgt = src.to(device), tgt.to(device)
                logits = model(src, tgt[:, :-1])
                val_loss += criterion(logits.view(-1, vocab_size), tgt[:, 1:].contiguous().view(-1)).item()
        avg_val = val_loss / len(val_loader)

        is_best = avg_val < best_val_loss
        logger.info(">>> Epoch %d/%d — Train : %.4f | Val : %.4f%s", epoch, args.epochs, avg_train, avg_val, " ★" if is_best else "")

        if is_best:
            best_val_loss = avg_val
            torch.save(model.state_dict(), output_dir / "model.pt")
            with open(output_dir / "config.pkl", "wb") as f:
                pickle.dump({
                    "vocab_size": vocab_size, "d_model": args.d_model,
                    "nhead": args.nhead, "num_layers": args.num_layers,
                    "ffn_dim": args.ffn_dim, "max_len": args.max_len,
                    "PAD_ID": PAD_ID, "BOS_ID": BOS_ID, "EOS_ID": EOS_ID,
                    "mode": "offline",
                }, f)
            logger.info("Modèle sauvegardé → %s", output_dir)

        # Aperçu toutes les 5 epochs
        if epoch % 5 == 0 or epoch == args.epochs:
            _preview_offline(model, sp, device, data[:3], args.max_len)

    logger.info("=" * 60)
    logger.info("Entraînement terminé ! Val loss : %.4f | Modèle : %s", best_val_loss, output_dir)
    logger.info("Redémarrez le serveur pour activer le moteur NMT.")
    logger.info("=" * 60)


def _preview_offline(model, sp, device, samples, max_len):
    import torch
    import sentencepiece as spm

    PAD_ID = sp.pad_id()
    BOS_ID = sp.bos_id()
    EOS_ID = sp.eos_id()

    def encode(text):
        ids = [BOS_ID] + sp.encode(text, out_type=int) + [EOS_ID]
        if len(ids) > max_len:
            ids = ids[:max_len - 1] + [EOS_ID]
        return ids + [PAD_ID] * (max_len - len(ids))

    logger.info("--- Aperçu ---")
    model.eval()
    for fr, ref_ba in samples:
        src = torch.tensor([encode(fr)], device=device)
        pred_ids = model.generate(src, max_len)
        pred = sp.decode([i for i in pred_ids if i not in (EOS_ID, PAD_ID)])
        logger.info("  FR  : %s", fr[:80])
        logger.info("  NMT : %s", pred[:80])
        logger.info("  REF : %s", ref_ba[:80])
    logger.info("--------------")


# ===========================================================================
# MODE 2 — Fine-tuning MarianMT (nécessite token HuggingFace)
# ===========================================================================

def train_marian(args: argparse.Namespace) -> None:
    import torch
    from torch.utils.data import DataLoader, Dataset
    from torch.optim import AdamW
    from transformers import MarianMTModel, MarianTokenizer, get_linear_schedule_with_warmup

    if args.hf_token:
        import os
        os.environ["HF_TOKEN"] = args.hf_token

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device : %s | Mode : MarianMT", device)

    data = load_corpus()
    random.seed(42)
    random.shuffle(data)
    split = max(10, int(len(data) * 0.9))
    train_data, val_data = data[:split], data[split:]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Source du checkpoint : --source-dir si fourni, sinon output_dir
    source_dir = Path(args.source_dir) if args.source_dir else output_dir

    # ---- Chargement : checkpoint existant (--resume) ou modèle de base ----
    resuming = args.resume and (source_dir / "config.pkl").exists() and (source_dir / "model.safetensors").exists()

    if resuming:
        logger.info("Reprise depuis le checkpoint : %s", source_dir)
        tokenizer = MarianTokenizer.from_pretrained(str(source_dir))
        model     = MarianMTModel.from_pretrained(str(source_dir))
        with open(source_dir / "config.pkl", "rb") as f:
            prev_cfg = pickle.load(f)
        epochs_done  = prev_cfg.get("epochs_completed", 0)
        best_val_loss = float("inf")   # repart de inf : le staging accueille un nouveau meilleur
        logger.info(
            "Checkpoint chargé — %d epochs déjà complétées (reprise epoch %d).",
            epochs_done, epochs_done + 1,
        )
    else:
        token = args.hf_token or None
        logger.info("Téléchargement du modèle de base : %s", args.base_model)
        tokenizer = MarianTokenizer.from_pretrained(args.base_model, token=token)
        model     = MarianMTModel.from_pretrained(args.base_model, token=token)
        epochs_done   = 0
        best_val_loss = float("inf")

        # Étendre le vocabulaire pour les caractères Bassa (1ère fois seulement)
        bassa_texts = [ba for _, ba in data]
        vocab = set(tokenizer.get_vocab().keys())
        new_chars = sorted({ch for text in bassa_texts for ch in text if ch.strip() and ch not in vocab})
        if new_chars:
            tokenizer.add_tokens(new_chars)
            model.resize_token_embeddings(len(tokenizer))
            logger.info("%d tokens Bassa ajoutés.", len(new_chars))

    logger.info("Modèle chargé — %dM paramètres", sum(p.numel() for p in model.parameters()) // 1_000_000)
    model.to(device)

    # ---- Epochs restantes ----
    remaining = args.epochs - epochs_done
    if remaining <= 0:
        logger.info(
            "Entraînement déjà complet (%d/%d epochs). Rien à faire.",
            epochs_done, args.epochs,
        )
        return
    logger.info(
        "Epochs : %d restantes (complétées : %d / total demandé : %d)",
        remaining, epochs_done, args.epochs,
    )

    class TranslationDataset(Dataset):
        def __init__(self, pairs):
            sources = [fr for fr, _ in pairs]
            targets = [ba for _, ba in pairs]
            enc = tokenizer(sources, text_target=targets, max_length=args.max_len, truncation=True, padding="max_length", return_tensors="pt")
            self.input_ids = enc["input_ids"]
            self.attention_mask = enc["attention_mask"]
            labels = enc["labels"].clone()
            labels[labels == tokenizer.pad_token_id] = -100
            self.labels = labels

        def __len__(self): return len(self.input_ids)
        def __getitem__(self, i): return {"input_ids": self.input_ids[i], "attention_mask": self.attention_mask[i], "labels": self.labels[i]}

    train_ds = TranslationDataset(train_data)
    val_ds   = TranslationDataset(val_data)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size)

    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = len(train_loader) * remaining
    # Pas de warmup en reprise : le modèle est déjà fine-tuné
    warmup_steps = 0 if resuming else max(1, total_steps // 10)
    scheduler = get_linear_schedule_with_warmup(optimizer, warmup_steps, total_steps)

    logger.info("Entraînement MarianMT — epochs %d→%d, batch=%d", epochs_done + 1, args.epochs, args.batch_size)
    for epoch in range(epochs_done + 1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        for step, batch in enumerate(train_loader, 1):
            batch = {k: v.to(device) for k, v in batch.items()}
            loss = model(**batch).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step(); scheduler.step(); optimizer.zero_grad()
            train_loss += loss.item()
            if step % 50 == 0 or step == len(train_loader):
                logger.info("Epoch %d/%d | Step %d/%d | Loss : %.4f", epoch, args.epochs, step, len(train_loader), train_loss / step)

        model.eval()
        val_loss = sum(model(**{k: v.to(device) for k, v in b.items()}).loss.item() for b in val_loader) / len(val_loader)
        is_best = val_loss < best_val_loss
        logger.info(">>> Epoch %d/%d — Val : %.4f%s", epoch, args.epochs, val_loss, " ★" if is_best else "")

        if is_best:
            best_val_loss = val_loss
            # Sauvegarde dans nmt_fr_bassa_staging/ pour éviter tout conflit
            # de memory-map si le serveur FastAPI a le modèle ouvert (Windows).
            staging_dir = output_dir.parent / (output_dir.name + "_staging")
            staging_dir.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(str(staging_dir))
            tokenizer.save_pretrained(str(staging_dir))
            with open(staging_dir / "config.pkl", "wb") as f:
                pickle.dump({
                    "mode": "marian",
                    "epochs_completed": epoch,
                    "best_val_loss": best_val_loss,
                }, f)
            logger.info("Modèle sauvegardé (staging) → %s", staging_dir)

            # Copie vers output_dir seulement si le serveur est arrêté
            import shutil
            if _is_server_running():
                logger.warning(
                    "Serveur FastAPI actif sur :8000 — copie différée.\n"
                    "  Arrêtez le serveur puis exécutez :\n"
                    '      robocopy "%s" "%s" /E /IS',
                    staging_dir, output_dir,
                )
            else:
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    for src_file in staging_dir.iterdir():
                        shutil.copy2(str(src_file), str(output_dir / src_file.name))
                    logger.info("Modèle copié automatiquement → %s (serveur arrêté)", output_dir)
                except OSError as copy_err:
                    logger.warning(
                        "Erreur lors de la copie : %s\n"
                        '  → robocopy "%s" "%s" /E /IS',
                        copy_err, staging_dir, output_dir,
                    )

    logger.info("Terminé ! Val loss : %.4f | Modèle : %s", best_val_loss, output_dir)


# ===========================================================================
# Point d'entrée
# ===========================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Entraînement NMT fr→Bassa")
    parser.add_argument("--epochs",     type=int,   default=10,        help="Total d'epochs (défaut : 10 pour MarianMT, 20 pour offline)")
    parser.add_argument("--batch-size", type=int,   default=64,        help="Batch size (défaut : 64)")
    parser.add_argument("--max-len",    type=int,   default=80,        help="Longueur max tokens (défaut : 80)")
    parser.add_argument("--lr",         type=float, default=1e-4,      help="Learning rate (défaut : 1e-4)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--source-dir", default="",
                        help="Dossier source du checkpoint à reprendre (défaut = output-dir)")
    # Architecture offline
    parser.add_argument("--d-model",    type=int,   default=256,       help="Dimension du modèle (défaut : 256)")
    parser.add_argument("--nhead",      type=int,   default=8,         help="Nombre de têtes d'attention (défaut : 8)")
    parser.add_argument("--num-layers", type=int,   default=4,         help="Nombre de couches (défaut : 4)")
    parser.add_argument("--ffn-dim",    type=int,   default=1024,      help="Dimension FFN (défaut : 1024)")
    parser.add_argument("--vocab-size", type=int,   default=8000,      help="Taille vocab SentencePiece (défaut : 8000)")
    # Mode MarianMT
    parser.add_argument("--hf-token",   default="",                    help="Token HuggingFace pour télécharger MarianMT depuis Helsinki-NLP")
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL,    help="Modèle de base HuggingFace (défaut : opus-mt-fr-kg, langue bantoue Kongo)")
    parser.add_argument("--resume",     action="store_true",           help="Reprendre l'entraînement depuis le checkpoint existant dans output-dir")
    args = parser.parse_args()

    try:
        import torch
        from transformers import get_linear_schedule_with_warmup
        import sentencepiece
    except ImportError as e:
        logger.error("Dépendance manquante : %s", e)
        logger.error("Installez : pip install torch transformers sentencepiece")
        sys.exit(1)

    if args.hf_token or args.resume:
        logger.info(
            "Mode : MarianMT (%s)",
            "reprise checkpoint" if args.resume else f"fine-tuning depuis {args.base_model}",
        )
        train_marian(args)
    else:
        logger.info("Mode : Transformer from scratch (hors-ligne)")
        train_offline(args)
