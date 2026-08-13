"""Point d'entrée en ligne de commande."""

import argparse
import sys
from pathlib import Path

from infrastructure_analyzer import run_pipeline
from infrastructure_analyzer.config import DEFAULT_OLLAMA_MODEL


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse un fichier JSON de métriques d’infrastructure."
    )
    parser.add_argument(
        "--input",
        default="rapport.json",
        help="Fichier JSON à analyser (défaut : rapport.json).",
    )
    parser.add_argument(
        "--output",
        default="output.json",
        help="Fichier JSON à générer (défaut : output.json).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_OLLAMA_MODEL,
        help=f"Modèle Ollama à utiliser (défaut : {DEFAULT_OLLAMA_MODEL}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    try:
        report = run_pipeline(args.input, args.model)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            report.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1

    print(f"Rapport généré : {output_path.resolve()}")
    print(f"Anomalies détectées : {len(report.anomalies)}")
    print(f"Recommandations générées : {len(report.recommendations)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
