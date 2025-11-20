
import sys
import logging
import argparse
from src.train import train_model
from src.predict import main as run_predictions

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("runner")
# -- imports obrigatórios

# -- imports opcionais (existem em alguns repos, noutros não)
_update_hist = None
try:
    # Se tiveres uma função explícita para atualizar histórico, usa-a
    from src.api_fetch import update_historical_data as _update_hist  # type: ignore
except Exception:
    _update_hist = None

_check_results = None
try:
    from scripts.check_results import main as _check_results  # type: ignore
except Exception:
    _check_results = None


def do_update_historical():
    if _update_hist is None:
        log.warning("⚠️  update_historical_data() não existe em src.api_fetch — a prosseguir sem esta etapa.")
        return
    log.info("🔄 A atualizar dados históricos…")
    _update_hist()


def do_train():
    log.info("🛠️  A treinar modelos…")
    train_model()


def do_predict():
    log.info("⚽  A gerar previsões…")
    run_predictions()


def do_check_results():
    if _check_results is None:
        log.warning("⚠️  check_results() não existe em scripts.check_results — a prosseguir sem esta etapa.")
        return
    log.info("🧪 A verificar resultados…")
    _check_results()


def main():
    parser = argparse.ArgumentParser(
        description="Runner CLI: train / predict / full (histórico + treino + previsões [+ check_results opcional])"
    )
    parser.add_argument("--mode", choices=["train", "predict", "full"], required=True)
    args = parser.parse_args()

    try:
        if args.mode == "train":
            # se tiveres histórico, atualiza antes do treino
            do_update_historical()
            do_train()

        elif args.mode == "predict":
            do_predict()

        elif args.mode == "full":
            do_update_historical()
            do_train()
            do_predict()
            do_check_results()

        log.info("✅ Concluído sem erros.")
    except Exception:
        log.exception("❌ Falhou a execução.")
        sys.exit(1)


if __name__ == "__main__":
    main()
